from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest
from fastapi.testclient import TestClient

import app.api.external_ai as external_ai_api
import app.core.redis as redis_module
import app.core.security as security_module
import app.core.settings as settings_module
import app.services.identity as identity_module
import app.services.memory as memory_module
import app.services.vault as vault_module
from app.services.external_ai import ExternalAIError, ExternalAIRateLimitError, ExternalAIResult


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
        self.model_router_free_provider = "groq"
        self.model_router_paid_provider = "openrouter"
        self.external_ai_anonymize_enabled = True
        self.groq_api_key = ""
        self.groq_api_url = ""
        self.groq_model = ""
        self.groq_rpm = 60
        self.groq_cost_input_per_1k = 0.0
        self.groq_cost_output_per_1k = 0.0
        self.gemini_api_key = ""
        self.gemini_api_url = ""
        self.gemini_model = ""
        self.gemini_rpm = 60
        self.gemini_cost_input_per_1k = 0.0
        self.gemini_cost_output_per_1k = 0.0
        self.openrouter_api_key = ""
        self.openrouter_api_url = ""
        self.openrouter_model = ""
        self.openrouter_rpm = 60
        self.openrouter_cost_input_per_1k = 0.0
        self.openrouter_cost_output_per_1k = 0.0

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


def test_external_ai_chat_success(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))
    token = _token(client, "operator", "operator")

    async def _fake_send_chat(**_kwargs):
        return ExternalAIResult(
            provider="groq",
            model="llama-3.1-8b-instant",
            reply="Merhaba",
            input_tokens=12,
            output_tokens=8,
            cost_usd=0.0,
            anonymized=True,
        )

    monkeypatch.setattr(external_ai_api, "send_chat", _fake_send_chat)
    resp = client.post(
        "/external-ai/chat",
        json={"provider": "groq", "message": "selam"},
        headers={"X-Session-Token": token},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "groq"
    assert body["usage"]["input_tokens"] == 12


def test_external_ai_chat_requires_operator_or_admin(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))
    token = _token(client, "viewer", "viewer")
    resp = client.post(
        "/external-ai/chat",
        json={"provider": "groq", "message": "selam"},
        headers={"X-Session-Token": token},
    )
    assert resp.status_code == 403


def test_external_ai_chat_rate_limit(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))
    token = _token(client, "operator", "operator")

    async def _fake_send_chat(**_kwargs):
        raise ExternalAIRateLimitError("limit")

    monkeypatch.setattr(external_ai_api, "send_chat", _fake_send_chat)
    resp = client.post(
        "/external-ai/chat",
        json={"provider": "groq", "message": "selam"},
        headers={"X-Session-Token": token},
    )
    assert resp.status_code == 429


def test_external_ai_chat_provider_error(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))
    token = _token(client, "operator", "operator")

    async def _fake_send_chat(**_kwargs):
        raise ExternalAIError("provider down")

    monkeypatch.setattr(external_ai_api, "send_chat", _fake_send_chat)
    resp = client.post(
        "/external-ai/chat",
        json={"provider": "groq", "message": "selam"},
        headers={"X-Session-Token": token},
    )
    assert resp.status_code == 502
