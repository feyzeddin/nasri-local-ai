from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest
from fastapi.testclient import TestClient

import app.api.matter as matter_api
import app.core.redis as redis_module
import app.core.security as security_module
import app.core.settings as settings_module
import app.services.identity as identity_module
import app.services.memory as memory_module
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
        self.matter_enabled = True
        self.matter_controller_url = "http://localhost:5580"
        self.matter_controller_token = ""

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
    return fake


def _make_client(monkeypatch, settings: _Settings) -> TestClient:
    monkeypatch.setattr(settings_module, "get_settings", lambda: settings)
    monkeypatch.setattr(security_module, "get_settings", lambda: settings)
    monkeypatch.setattr(identity_module, "get_settings", lambda: settings)
    monkeypatch.setattr(vault_module, "get_settings", lambda: settings)
    monkeypatch.setattr(memory_module, "get_settings", lambda: settings)
    monkeypatch.setattr(matter_api, "get_settings", lambda: settings)
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


def test_matter_status_devices_pair_action(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))
    op = _token(client, "operator", "operator")
    vw = _token(client, "viewer", "viewer")

    async def _status():
        return True, "online"

    async def _devices():
        return [{"device_id": "dev-1", "name": "Salon Lamba", "device_type": "light"}]

    async def _pair(_code, _network_hint):
        return True, "paired"

    async def _action(device_id, action, value=None):
        return True, f"{device_id}:{action}"

    monkeypatch.setattr(matter_api, "controller_status", _status)
    monkeypatch.setattr(matter_api, "list_devices", _devices)
    monkeypatch.setattr(matter_api, "pair_device", _pair)
    monkeypatch.setattr(matter_api, "send_action", _action)

    assert client.get("/matter/status", headers={"X-Session-Token": vw}).status_code == 200
    assert client.get("/matter/devices", headers={"X-Session-Token": vw}).json()["count"] == 1
    assert (
        client.post("/matter/pair", json={"code": "123-45-678"}, headers={"X-Session-Token": op}).status_code
        == 200
    )
    assert (
        client.post(
            "/matter/action",
            json={"device_id": "dev-1", "action": "turn_on"},
            headers={"X-Session-Token": op},
        ).status_code
        == 200
    )


def test_matter_operator_only_for_pair(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))
    vw = _token(client, "viewer", "viewer")
    resp = client.post("/matter/pair", json={"code": "123456"}, headers={"X-Session-Token": vw})
    assert resp.status_code == 403

