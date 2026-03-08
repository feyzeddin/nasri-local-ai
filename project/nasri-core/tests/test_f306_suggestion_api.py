from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest
from fastapi.testclient import TestClient

import app.api.suggestion as suggestion_api
import app.core.redis as redis_module
import app.core.security as security_module
import app.core.settings as settings_module
import app.services.identity as identity_module
import app.services.memory as memory_module
import app.services.vault as vault_module


class _Settings:
    redis_host = "localhost"
    redis_port = 6379
    ollama_url = "http://localhost:11434"
    model_name = "llama3"
    max_history_pairs = 10
    session_ttl_seconds = 3600
    system_prompt = None
    api_key = None
    cors_origins = ["http://localhost:5173"]
    rate_limit_rpm = 60
    rbac_enabled = False
    auth_session_ttl_seconds = 3600
    users = {}
    suggestion_enabled = True
    suggestion_max_items = 5

    def __getattr__(self, _name: str):
        # Uygulama genelinde istenen diğer ayarlar için güvenli varsayılan.
        return ""

    def vault_key_bytes(self) -> bytes:
        import hashlib

        return hashlib.sha256("k".encode("utf-8")).digest()


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_module, "get_redis", lambda: fake)
    monkeypatch.setattr(security_module, "get_redis", lambda: fake)
    monkeypatch.setattr(identity_module, "get_redis", lambda: fake)
    monkeypatch.setattr(vault_module, "get_redis", lambda: fake)
    return fake


def _make_client(monkeypatch) -> TestClient:
    s = _Settings()
    monkeypatch.setattr(settings_module, "get_settings", lambda: s)
    monkeypatch.setattr(security_module, "get_settings", lambda: s)
    monkeypatch.setattr(identity_module, "get_settings", lambda: s)
    monkeypatch.setattr(vault_module, "get_settings", lambda: s)
    monkeypatch.setattr(memory_module, "get_settings", lambda: s)
    import app.api.files as files_module
    import app.api.speech as speech_module
    import app.main as main_module

    monkeypatch.setattr(files_module, "get_settings", lambda: s)
    monkeypatch.setattr(speech_module, "get_settings", lambda: s)
    monkeypatch.setattr(main_module, "get_settings", lambda: s)
    monkeypatch.setattr(main_module, "start_maintenance_worker", lambda: None)

    async def _noop_stop() -> None:
        return

    monkeypatch.setattr(main_module, "stop_maintenance_worker", _noop_stop)
    app = main_module._create_app()
    return TestClient(app)


def test_proactive_suggestions_success(monkeypatch):
    client = _make_client(monkeypatch)
    monkeypatch.setattr(
        suggestion_api,
        "generate_proactive_suggestions",
        lambda _profile_id: [
            type("S", (), {"title": "Öneri", "reason": "Sebep", "priority": 4})()
        ],
    )
    resp = client.get("/suggestions/proactive?profile_id=feyza")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
