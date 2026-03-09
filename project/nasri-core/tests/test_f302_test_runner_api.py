from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest
from fastapi.testclient import TestClient

import app.api.test_runner as tr_api
import app.core.redis as redis_module
import app.core.security as security_module
import app.core.settings as settings_module
import app.services.identity as identity_module
import app.services.memory as memory_module
import app.services.test_runner as tr_service
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
        self.test_runner_enabled = True
        self.test_runner_default_target = "tests"
        self.test_runner_max_output_chars = 6000

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
    monkeypatch.setattr(tr_service, "get_redis", lambda: fake)
    return fake


def _make_client(monkeypatch, settings: _Settings) -> TestClient:
    monkeypatch.setattr(settings_module, "get_settings", lambda: settings)
    monkeypatch.setattr(security_module, "get_settings", lambda: settings)
    monkeypatch.setattr(identity_module, "get_settings", lambda: settings)
    monkeypatch.setattr(vault_module, "get_settings", lambda: settings)
    monkeypatch.setattr(memory_module, "get_settings", lambda: settings)
    monkeypatch.setattr(tr_service, "get_settings", lambda: settings)
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


def test_test_runner_run_status_history(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))
    op = _token(client, "operator", "operator")
    vw = _token(client, "viewer", "viewer")

    async def _fake_run_tests(**_kwargs):
        return {
            "run_id": "r1",
            "command": ["pytest", "-q", "tests"],
            "target": "tests",
            "keyword": None,
            "return_code": 0,
            "ok": True,
            "duration_ms": 120,
            "output": "ok",
            "started_at": "2026-03-08T00:00:00+00:00",
        }

    async def _fake_last():
        return {
            "run_id": "r1",
            "command": ["pytest", "-q", "tests"],
            "target": "tests",
            "keyword": None,
            "return_code": 0,
            "ok": True,
            "duration_ms": 120,
            "output": "ok",
            "started_at": "2026-03-08T00:00:00+00:00",
        }

    async def _fake_history(limit=10):
        return [await _fake_last()]

    monkeypatch.setattr(tr_api, "run_tests", _fake_run_tests)
    monkeypatch.setattr(tr_api, "get_last_result", _fake_last)
    monkeypatch.setattr(tr_api, "list_history", _fake_history)

    run = client.post("/test-runner/run", json={"target": "tests"}, headers={"X-Session-Token": op})
    assert run.status_code == 200
    assert run.json()["ok"] is True

    status = client.get("/test-runner/status", headers={"X-Session-Token": vw})
    assert status.status_code == 200
    assert status.json()["last_run"]["run_id"] == "r1"

    history = client.get("/test-runner/history?limit=5", headers={"X-Session-Token": vw})
    assert history.status_code == 200
    assert history.json()["count"] == 1


def test_test_runner_run_forbidden_for_viewer(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))
    vw = _token(client, "viewer", "viewer")
    resp = client.post("/test-runner/run", json={"target": "tests"}, headers={"X-Session-Token": vw})
    assert resp.status_code == 403

