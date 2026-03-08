from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest
from fastapi.testclient import TestClient

import app.api.ssh as ssh_api
import app.core.redis as redis_module
import app.core.security as security_module
import app.core.settings as settings_module
import app.services.identity as identity_module
import app.services.memory as memory_module
import app.services.vault as vault_module
from app.services.ssh import SSHError, SSHProfile


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
        self.lan_scan_default_cidr = "192.168.1.0/24"
        self.lan_scan_timeout_seconds = 30
        self.lan_scan_mdns_enabled = True
        self.ssh_connect_timeout_seconds = 15

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


def test_ssh_profile_create_and_exec(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))
    token = _token(client, "operator", "operator")

    async def _fake_save(**kwargs):
        return SSHProfile(
            profile_name=kwargs["profile_name"],
            host=kwargs["host"],
            port=kwargs["port"],
            username=kwargs["username"],
            auth_method=kwargs["auth_method"],
        )

    async def _fake_exec(**_kwargs):
        return 0, "ok", ""

    monkeypatch.setattr(ssh_api, "save_profile", _fake_save)
    monkeypatch.setattr(ssh_api, "exec_command", _fake_exec)

    create_resp = client.post(
        "/ssh/profiles",
        json={
            "profile_name": "srv1",
            "host": "192.168.1.10",
            "port": 22,
            "username": "root",
            "auth_method": "password",
            "password": "secret",
        },
        headers={"X-Session-Token": token},
    )
    assert create_resp.status_code == 200

    exec_resp = client.post(
        "/ssh/exec",
        json={"profile_name": "srv1", "command": "uptime", "timeout_seconds": 15},
        headers={"X-Session-Token": token},
    )
    assert exec_resp.status_code == 200
    assert exec_resp.json()["stdout"] == "ok"


def test_ssh_viewer_forbidden(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))
    token = _token(client, "viewer", "viewer")
    resp = client.post(
        "/ssh/exec",
        json={"profile_name": "srv1", "command": "uptime", "timeout_seconds": 15},
        headers={"X-Session-Token": token},
    )
    assert resp.status_code == 403


def test_ssh_exec_error(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))
    token = _token(client, "operator", "operator")

    async def _fake_exec(**_kwargs):
        raise SSHError("bağlantı yok")

    monkeypatch.setattr(ssh_api, "exec_command", _fake_exec)
    resp = client.post(
        "/ssh/exec",
        json={"profile_name": "srv1", "command": "uptime", "timeout_seconds": 15},
        headers={"X-Session-Token": token},
    )
    assert resp.status_code == 502
