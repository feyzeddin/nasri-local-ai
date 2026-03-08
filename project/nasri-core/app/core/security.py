"""Güvenlik katmanı — F12.

F12.1 — API Key doğrulaması
    NASRI_API_KEY env ayarlanmışsa tüm /chat endpoint'leri
    'Authorization: Bearer <key>' başlığını zorunlu kılar.
    Ayarlanmamışsa auth devre dışıdır (geliştirme modu).

F12.3 — Hız sınırlaması (Rate Limiting)
    In-memory sliding window: per-IP, dakikada NASRI_RATE_LIMIT_RPM istek.
    429 Too Many Requests döner; 'Retry-After' başlığı saniye olarak eklenir.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.settings import get_settings

# ---------------------------------------------------------------------------
# F12.1 — API Key
# ---------------------------------------------------------------------------

_bearer_scheme = HTTPBearer(auto_error=False)


def verify_api_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """API key doğrulama dependency'si.

    - NASRI_API_KEY ayarlı değilse: her zaman geçer (dev modu).
    - Ayarlıysa: Authorization: Bearer <key> eşleşmeli.
    """
    expected = get_settings().api_key
    if expected is None:
        return  # Auth devre dışı

    if credentials is None or credentials.credentials != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz veya eksik API anahtarı.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# F12.3 — Rate Limiter (sliding window, in-memory)
# ---------------------------------------------------------------------------


class _RateLimiter:
    """Thread-safe per-IP sliding window rate limiter."""

    def __init__(self) -> None:
        # IP → deque of request timestamps (float, seconds)
        self._windows: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def is_allowed(self, ip: str, rpm: int) -> tuple[bool, int]:
        """İsteğin izin verilip verilmediğini döner.

        Returns:
            (allowed, retry_after_seconds)
            retry_after_seconds: izin verilmezse kaç saniye beklemeli.
        """
        now = time.monotonic()
        window_start = now - 60.0

        with self._lock:
            dq = self._windows[ip]
            # Pencere dışına düşen zaman damgalarını temizle
            while dq and dq[0] < window_start:
                dq.popleft()

            if len(dq) >= rpm:
                # En eski isteğin bitmesine kaç saniye kaldı
                retry_after = int(dq[0] - window_start) + 1
                return False, retry_after

            dq.append(now)
            return True, 0


_limiter = _RateLimiter()


def rate_limit(request: Request) -> None:
    """Rate limit dependency'si.

    İstemci IP'si X-Forwarded-For başlığından (reverse proxy arkasında)
    veya doğrudan bağlantıdan alınır.
    """
    settings = get_settings()
    rpm = settings.rate_limit_rpm

    forwarded = request.headers.get("X-Forwarded-For")
    ip = (
        forwarded.split(",")[0].strip()
        if forwarded
        else (request.client.host if request.client else "unknown")
    )

    allowed, retry_after = _limiter.is_allowed(ip, rpm)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Çok fazla istek. {retry_after} saniye sonra tekrar deneyin.",
            headers={"Retry-After": str(retry_after)},
        )
