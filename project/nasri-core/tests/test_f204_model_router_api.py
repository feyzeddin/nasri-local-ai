from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest
from fastapi.testclient import TestClient

import app.api.model_router as model_router_api
import app.core.redis as redis_module
import app.core.security as security_module
import app.core.settings as settings_module
import app.services.identity as identity_module
import app.services.memory as memory_module
import app.services.vault as vault_module
from app.services.model_router import ModelRouterError, RouterAttempt, RouterResult


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
        self.files_root = "."
        self.files_max_results = 200
        self.whisper_cpp_binary = "whisper"
        self.whisper_cpp_model = "model.bin"
        self.whisper_cpp_language = "tr"
        self.whisper_cpp_timeout_seconds = 120
        self.piper_binary = "piper"
        self.piper_model = "model.onnx"
        self.piper_output_sample_rate = 22050
        self.piper_timeout_seconds = 120
        self.vault_master_key = "super-secret-master-key"
        self.vault_key_id = "v1"
        self.device_fingerprint_salt = "device-salt"
        self.biometric_salt = "bio-salt"
        self.rag_collection_name = "nasri_docs"
        self.rag_persist_dir = ".nasri-rag"
        self.rag_embedding_model = "nomic-embed-text"
        self.rag_default_top_k = 5
        self.memory_collection_name = "nasri_memory"
        self.memory_default_top_k = 5
        self.planner_max_steps = 6
        self.model_router_tier_order = "local,free,paid"
        self.model_router_free_enabled = True
        self.model_router_free_api_url = ""
        self.model_router_free_api_key = ""
        self.model_router_free_model = ""
        self.model_router_paid_enabled = False
        self.model_router_paid_api_url = ""
        self.model_router_paid_api_key = ""
        self.model_router_paid_model = ""

    def vault_key_bytes(self) -> bytes:
        import hashlib

        return hashlib.sha256(self.vault_master_key.encode("utf-8")).digest()


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
    import app.api.files as files_module
    import app.api.speech as speech_module
    import app.main as main_module

    monkeypatch.setattr(files_module, "get_settings", lambda: settings)
    monkeypatch.setattr(speech_module, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    app = main_module._create_app()
    return TestClient(app)


def _token(client: TestClient, username: str, password: str) -> str:
    resp = client.post("/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_model_router_chat_success(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))
    token = _token(client, "viewer", "viewer")

    async def _fake_route_chat(**_kwargs):
        return RouterResult(
            reply="Merhaba, routed.",
            used_tier="local",
            attempts=[RouterAttempt(tier="local", status="ok", detail=None)],
        )

    monkeypatch.setattr(model_router_api, "route_chat", _fake_route_chat)
    resp = client.post(
        "/model-router/chat",
        json={"message": "selam"},
        headers={"X-Session-Token": token},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["reply"] == "Merhaba, routed."
    assert data["used_tier"] == "local"
    assert data["attempts"][0]["status"] == "ok"


def test_model_router_chat_requires_auth(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))
    resp = client.post("/model-router/chat", json={"message": "selam"})
    assert resp.status_code == 403


def test_model_router_chat_returns_502_on_router_error(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))
    token = _token(client, "viewer", "viewer")

    async def _fake_route_chat(**_kwargs):
        raise ModelRouterError("fallback katmanları başarısız")

    monkeypatch.setattr(model_router_api, "route_chat", _fake_route_chat)
    resp = client.post(
        "/model-router/chat",
        json={"message": "selam"},
        headers={"X-Session-Token": token},
    )
    assert resp.status_code == 502
    assert "başarısız" in resp.json()["detail"]
