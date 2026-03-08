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

import json
from dataclasses import dataclass
from secrets import token_urlsafe
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.settings import get_settings
from app.core.redis import get_redis

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


# ---------------------------------------------------------------------------
# F1.07 — Session Auth + RBAC
# ---------------------------------------------------------------------------


@dataclass
class AuthSession:
    username: str
    role: str
    token: str


_AUTH_PREFIX = "auth:session"


def _auth_key(token: str) -> str:
    return f"{_AUTH_PREFIX}:{token}"


async def create_auth_session(username: str, role: str) -> tuple[str, int]:
    token = token_urlsafe(32)
    ttl = get_settings().auth_session_ttl_seconds
    payload = {"username": username, "role": role}
    r = get_redis()
    await r.setex(_auth_key(token), ttl, json.dumps(payload, ensure_ascii=False))
    return token, ttl


async def validate_user_credentials(username: str, password: str) -> str | None:
    users = get_settings().users
    item = users.get(username)
    if item is None:
        return None
    if item.get("password") != password:
        return None
    return item.get("role", "viewer")


async def delete_auth_session(token: str) -> None:
    r = get_redis()
    await r.delete(_auth_key(token))


async def get_current_session(request: Request) -> AuthSession:
    settings = get_settings()
    if not settings.rbac_enabled:
        return AuthSession(username="local-dev", role="admin", token="dev")

    token = request.headers.get("X-Session-Token")
    if not token:
        # RBAC endpointleri için Authorization Bearer da kabul edilir
        credentials = await _bearer_scheme(request)
        token = credentials.credentials if credentials else None

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Oturum token'i gerekli.",
        )

    r = get_redis()
    raw = await r.get(_auth_key(token))
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz veya süresi dolmuş oturum.",
        )

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bozuk oturum verisi.",
        ) from exc

    # Sliding expiration: aktif kullanımda TTL yenilenir
    await r.expire(_auth_key(token), settings.auth_session_ttl_seconds)
    return AuthSession(
        username=str(payload.get("username", "")),
        role=str(payload.get("role", "viewer")),
        token=token,
    )


def require_roles(*roles: str):
    allowed = set(roles)

    async def _dep(session: AuthSession = Depends(get_current_session)) -> AuthSession:
        if session.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Bu işlem için rol gerekli: {', '.join(sorted(allowed))}",
            )
        return session

    return _dep
