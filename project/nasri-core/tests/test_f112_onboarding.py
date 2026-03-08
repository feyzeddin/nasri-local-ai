from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest
from fastapi.testclient import TestClient

import app.core.redis as redis_module
import app.core.security as security_module
import app.core.settings as settings_module


class _Settings:
    def __init__(self) -> None:
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
        self.rbac_enabled = False
        self.auth_session_ttl_seconds = 3600
        self.users = {"admin": {"password": "admin", "role": "admin"}}
        self.files_root = "."
        self.files_max_results = 200


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    import app.api.onboarding as onboarding_module

    monkeypatch.setattr(redis_module, "get_redis", lambda: fake)
    monkeypatch.setattr(security_module, "get_redis", lambda: fake)
    monkeypatch.setattr(onboarding_module, "get_redis", lambda: fake)
    return fake


def _client(monkeypatch) -> TestClient:
    settings = _Settings()
    monkeypatch.setattr(settings_module, "get_settings", lambda: settings)
    monkeypatch.setattr(security_module, "get_settings", lambda: settings)
    import app.api.files as files_module
    import app.main as main_module

    monkeypatch.setattr(files_module, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    app = main_module._create_app()
    return TestClient(app)


def test_onboarding_start_and_answer_flow(monkeypatch):
    client = _client(monkeypatch)

    start = client.post("/onboarding/start", json={})
    assert start.status_code == 200
    data = start.json()
    assert data["step"] == 0
    assert data["completed"] is False
    assert data["next_question"] is not None
    sid = data["session_id"]

    a1 = client.post("/onboarding/answer", json={"session_id": sid, "answer": "Feyza"})
    assert a1.status_code == 200
    assert a1.json()["step"] == 1
    assert a1.json()["answers"]["q1"] == "Feyza"

    a2 = client.post("/onboarding/answer", json={"session_id": sid, "answer": "Yazilim"})
    assert a2.status_code == 200
    assert a2.json()["step"] == 2

    a3 = client.post(
        "/onboarding/answer",
        json={"session_id": sid, "answer": "local-only"},
    )
    assert a3.status_code == 200
    assert a3.json()["completed"] is True
    assert a3.json()["next_question"] is None


def test_onboarding_get_returns_404_for_missing_session(monkeypatch):
    client = _client(monkeypatch)
    resp = client.get("/onboarding/unknown")
    assert resp.status_code == 404
