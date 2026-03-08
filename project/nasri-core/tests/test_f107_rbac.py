from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest
from fastapi.testclient import TestClient

import app.core.redis as redis_module
import app.core.security as security_module
import app.core.settings as settings_module


class _Settings:
    def __init__(self, rbac_enabled: bool = True) -> None:
        self.redis_host = "localhost"
        self.redis_port = 6379
        self.ollama_url = "http://localhost:11434"
        self.model_name = "llama3"
        self.max_history_pairs = 10
        self.session_ttl_seconds = 3600
        self.system_prompt = None
        self.api_key = None
        self.cors_origins = ["http://localhost:5173"]
        self.rate_limit_rpm = 60
        self.rbac_enabled = rbac_enabled
        self.auth_session_ttl_seconds = 1800
        self.users = {
            "admin": {"password": "admin", "role": "admin"},
            "viewer": {"password": "viewer", "role": "viewer"},
        }


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_module, "get_redis", lambda: fake)
    monkeypatch.setattr(security_module, "get_redis", lambda: fake)
    return fake


def _make_client(monkeypatch, settings: _Settings) -> TestClient:
    monkeypatch.setattr(settings_module, "get_settings", lambda: settings)
    monkeypatch.setattr(security_module, "get_settings", lambda: settings)

    import app.main as main_module

    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    app = main_module._create_app()
    return TestClient(app)


def test_login_and_me_success(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))
    login = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = client.get("/auth/me", headers={"X-Session-Token": token})
    assert me.status_code == 200
    assert me.json()["username"] == "admin"
    assert me.json()["role"] == "admin"


def test_me_requires_session_when_rbac_enabled(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_config_forbidden_for_viewer(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))
    login = client.post("/auth/login", json={"username": "viewer", "password": "viewer"})
    token = login.json()["access_token"]

    resp = client.get("/config", headers={"X-Session-Token": token})
    assert resp.status_code == 403


def test_config_allowed_for_admin(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))
    login = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    token = login.json()["access_token"]

    resp = client.get("/config", headers={"X-Session-Token": token})
    assert resp.status_code == 200
    assert "redis_host" in resp.json()
