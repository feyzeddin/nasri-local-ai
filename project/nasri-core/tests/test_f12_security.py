"""F12 güvenlik testleri.

F12.1 — API Key doğrulaması
F12.2 — CORS başlıkları
F12.3 — Rate limiting

Redis: fakeredis, Ollama: respx mock'lu testlerde kullanılmaz.
"""

from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest
from fastapi.testclient import TestClient

import app.core.redis as redis_module
import app.core.security as security_module
import app.core.settings as settings_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Settings:
    """Parametreli sahte ayarlar."""

    def __init__(
        self,
        api_key: str | None = None,
        cors_origins: list[str] | None = None,
        rate_limit_rpm: int = 60,
    ) -> None:
        self.redis_host = "localhost"
        self.redis_port = 6379
        self.ollama_url = "http://localhost:11434"
        self.model_name = "llama3"
        self.max_history_pairs = 10
        self.session_ttl_seconds = 3600
        self.system_prompt = None
        self.api_key = api_key
        self.cors_origins = cors_origins or ["http://localhost:5173"]
        self.rate_limit_rpm = rate_limit_rpm


def _make_client(monkeypatch, settings: _Settings) -> TestClient:
    """Verilen ayarlarla yeni bir FastAPI app + TestClient döner."""
    monkeypatch.setattr(settings_module, "get_settings", lambda: settings)
    monkeypatch.setattr(security_module, "get_settings", lambda: settings)

    # App'i yeniden oluştur (main._create_app)
    import app.main as main_module

    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    new_app = main_module._create_app()
    return TestClient(new_app)


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_module, "get_redis", lambda: fake)
    return fake


# ---------------------------------------------------------------------------
# F12.1 — API Key
# ---------------------------------------------------------------------------


def test_auth_disabled_when_no_api_key_set(monkeypatch):
    """NASRI_API_KEY yoksa auth olmadan erişilebilmeli."""
    client = _make_client(monkeypatch, _Settings(api_key=None))
    resp = client.post("/chat/session", json={})
    assert resp.status_code == 201


def test_auth_required_when_api_key_set(monkeypatch):
    """NASRI_API_KEY ayarlıysa başlık olmadan 401 dönmeli."""
    client = _make_client(monkeypatch, _Settings(api_key="gizli"))
    resp = client.post("/chat/session", json={})
    assert resp.status_code == 401


def test_auth_accepted_with_correct_key(monkeypatch):
    """Doğru Bearer token ile 201 dönmeli."""
    client = _make_client(monkeypatch, _Settings(api_key="gizli"))
    resp = client.post(
        "/chat/session",
        json={},
        headers={"Authorization": "Bearer gizli"},
    )
    assert resp.status_code == 201


def test_auth_rejected_with_wrong_key(monkeypatch):
    """Yanlış token ile 401 dönmeli."""
    client = _make_client(monkeypatch, _Settings(api_key="gizli"))
    resp = client.post(
        "/chat/session",
        json={},
        headers={"Authorization": "Bearer yanlis"},
    )
    assert resp.status_code == 401


def test_health_exempt_from_auth(monkeypatch):
    """/health endpoint'i API key olmadan erişilebilmeli."""
    client = _make_client(monkeypatch, _Settings(api_key="gizli"))
    resp = client.get("/health")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# F12.2 — CORS
# ---------------------------------------------------------------------------


def test_cors_header_present_for_allowed_origin(monkeypatch):
    """İzin verilen origin için CORS başlığı dönmeli."""
    client = _make_client(
        monkeypatch,
        _Settings(cors_origins=["http://localhost:5173"]),
    )
    resp = client.options(
        "/chat/session",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_header_absent_for_disallowed_origin(monkeypatch):
    """İzin verilmeyen origin için CORS başlığı olmamalı."""
    client = _make_client(
        monkeypatch,
        _Settings(cors_origins=["http://localhost:5173"]),
    )
    resp = client.options(
        "/chat/session",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in resp.headers


# ---------------------------------------------------------------------------
# F12.3 — Rate Limiting
# ---------------------------------------------------------------------------


def test_rate_limit_allows_under_limit(monkeypatch):
    """Limit altındaki istekler geçmeli."""
    # Temiz bir limiter örneği kullan
    from app.core.security import _RateLimiter

    fresh = _RateLimiter()
    monkeypatch.setattr(security_module, "_limiter", fresh)

    client = _make_client(monkeypatch, _Settings(rate_limit_rpm=5))
    for _ in range(5):
        resp = client.post(
            "/chat/session",
            json={},
            headers={"X-Forwarded-For": "10.0.0.1"},
        )
        assert resp.status_code == 201


def test_rate_limit_blocks_over_limit(monkeypatch):
    """Limit aşılınca 429 dönmeli."""
    from app.core.security import _RateLimiter

    fresh = _RateLimiter()
    monkeypatch.setattr(security_module, "_limiter", fresh)

    client = _make_client(monkeypatch, _Settings(rate_limit_rpm=3))

    # İlk 3 — geçmeli
    for _ in range(3):
        client.post(
            "/chat/session",
            json={},
            headers={"X-Forwarded-For": "10.0.0.2"},
        )

    # 4. — 429 bekliyoruz
    resp = client.post(
        "/chat/session",
        json={},
        headers={"X-Forwarded-For": "10.0.0.2"},
    )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


def test_rate_limit_per_ip_independent(monkeypatch):
    """Farklı IP'ler birbirini etkilememeli."""
    from app.core.security import _RateLimiter

    fresh = _RateLimiter()
    monkeypatch.setattr(security_module, "_limiter", fresh)

    client = _make_client(monkeypatch, _Settings(rate_limit_rpm=1))

    # IP A limitini doldur
    client.post(
        "/chat/session",
        json={},
        headers={"X-Forwarded-For": "10.0.0.3"},
    )

    # IP B hâlâ serbest olmalı
    resp = client.post(
        "/chat/session",
        json={},
        headers={"X-Forwarded-For": "10.0.0.4"},
    )
    assert resp.status_code == 201
