from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest
from fastapi.testclient import TestClient

import app.api.federation as federation_api
import app.core.redis as redis_module
import app.core.security as security_module
import app.core.settings as settings_module
import app.services.identity as identity_module
import app.services.memory as memory_module
import app.services.federation as federation_service
import app.services.vault as vault_module


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
        self.auth_session_ttl_seconds = 3600
        self.users = {
            "admin": {"password": "admin", "role": "admin"},
            "operator": {"password": "operator", "role": "operator"},
            "viewer": {"password": "viewer", "role": "viewer"},
        }
        self.federation_enabled = True
        self.federation_node_id = "node-local"
        self.federation_shared_token = "shared-secret"

    def __getattr__(self, _name: str):
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
    monkeypatch.setattr(federation_service, "get_redis", lambda: fake)
    return fake


def _make_client(monkeypatch, settings: _Settings) -> TestClient:
    monkeypatch.setattr(settings_module, "get_settings", lambda: settings)
    monkeypatch.setattr(security_module, "get_settings", lambda: settings)
    monkeypatch.setattr(identity_module, "get_settings", lambda: settings)
    monkeypatch.setattr(vault_module, "get_settings", lambda: settings)
    monkeypatch.setattr(memory_module, "get_settings", lambda: settings)
    monkeypatch.setattr(federation_service, "get_settings", lambda: settings)
    import app.api.files as files_module
    import app.api.speech as speech_module
    import app.main as main_module

    monkeypatch.setattr(files_module, "get_settings", lambda: settings)
    monkeypatch.setattr(speech_module, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "start_maintenance_worker", lambda: None)

    async def _noop_stop() -> None:
        return

    monkeypatch.setattr(main_module, "stop_maintenance_worker", _noop_stop)
    app = main_module._create_app()
    return TestClient(app)


def _token(client: TestClient, username: str, password: str) -> str:
    resp = client.post("/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_federation_peer_crud_and_dispatch(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))
    admin = _token(client, "admin", "admin")
    op = _token(client, "operator", "operator")
    viewer = _token(client, "viewer", "viewer")

    async def _fake_dispatch_to_peer(**_kwargs):
        return 200, "ok"

    monkeypatch.setattr(federation_api, "dispatch_to_peer", _fake_dispatch_to_peer)

    create = client.post(
        "/federation/peers",
        json={"peer_id": "peer-1", "base_url": "http://peer.local"},
        headers={"X-Session-Token": op},
    )
    assert create.status_code == 200
    assert create.json()["has_token"] is False

    list_resp = client.get("/federation/peers", headers={"X-Session-Token": viewer})
    assert list_resp.status_code == 200
    assert list_resp.json()["count"] == 1

    dispatch = client.post(
        "/federation/dispatch",
        json={"peer_id": "peer-1", "path": "/federation/inbox", "payload": {"x": 1}},
        headers={"X-Session-Token": op},
    )
    assert dispatch.status_code == 200
    assert dispatch.json()["detail"] == "ok"

    delete = client.delete("/federation/peers/peer-1", headers={"X-Session-Token": admin})
    assert delete.status_code == 200
    assert delete.json()["deleted"] is True


def test_federation_rbac(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))
    viewer = _token(client, "viewer", "viewer")

    create = client.post(
        "/federation/peers",
        json={"peer_id": "peer-1", "base_url": "http://peer.local"},
        headers={"X-Session-Token": viewer},
    )
    assert create.status_code == 403

    delete = client.delete("/federation/peers/peer-1", headers={"X-Session-Token": viewer})
    assert delete.status_code == 403


def test_federation_inbox_token_guard(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))

    unauthorized = client.post(
        "/federation/inbox",
        json={"source_node_id": "peer-1", "payload": {"m": "x"}},
        headers={"X-Federation-Token": "wrong"},
    )
    assert unauthorized.status_code == 401

    ok = client.post(
        "/federation/inbox",
        json={"source_node_id": "peer-1", "payload": {"m": "x"}},
        headers={"X-Federation-Token": "shared-secret"},
    )
    assert ok.status_code == 200
    assert ok.json()["accepted"] is True
