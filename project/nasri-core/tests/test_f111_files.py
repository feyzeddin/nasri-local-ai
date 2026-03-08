from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest
from fastapi.testclient import TestClient

import app.core.redis as redis_module
import app.core.security as security_module
import app.core.settings as settings_module


class _Settings:
    def __init__(self, files_root: str) -> None:
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
        self.rbac_enabled = True
        self.auth_session_ttl_seconds = 3600
        self.users = {
            "admin": {"password": "admin", "role": "admin"},
            "operator": {"password": "operator", "role": "operator"},
            "viewer": {"password": "viewer", "role": "viewer"},
        }
        self.files_root = files_root
        self.files_max_results = 200


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_module, "get_redis", lambda: fake)
    monkeypatch.setattr(security_module, "get_redis", lambda: fake)
    return fake


def _client(monkeypatch, settings: _Settings) -> TestClient:
    monkeypatch.setattr(settings_module, "get_settings", lambda: settings)
    monkeypatch.setattr(security_module, "get_settings", lambda: settings)
    import app.api.files as files_module
    import app.main as main_module

    monkeypatch.setattr(files_module, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    app = main_module._create_app()
    return TestClient(app)


def _token(client: TestClient, username: str, password: str) -> str:
    resp = client.post("/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_files_list_and_search(monkeypatch, tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "notes.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "readme.md").write_text("x", encoding="utf-8")

    client = _client(monkeypatch, _Settings(files_root=str(tmp_path)))
    token = _token(client, "operator", "operator")
    headers = {"X-Session-Token": token}

    list_resp = client.get("/files/list", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["count"] >= 2

    search_resp = client.get("/files/search", params={"q": "note"}, headers=headers)
    assert search_resp.status_code == 200
    paths = [e["path"] for e in search_resp.json()["entries"]]
    assert any("notes.txt" in p for p in paths)


def test_files_forbidden_for_viewer(monkeypatch, tmp_path):
    client = _client(monkeypatch, _Settings(files_root=str(tmp_path)))
    token = _token(client, "viewer", "viewer")
    resp = client.get("/files/list", headers={"X-Session-Token": token})
    assert resp.status_code == 403


def test_files_reject_path_traversal(monkeypatch, tmp_path):
    client = _client(monkeypatch, _Settings(files_root=str(tmp_path)))
    token = _token(client, "admin", "admin")
    resp = client.get(
        "/files/list",
        params={"path": ".."},
        headers={"X-Session-Token": token},
    )
    assert resp.status_code == 400
