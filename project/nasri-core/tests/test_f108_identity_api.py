from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest
from fastapi.testclient import TestClient

import app.core.redis as redis_module
import app.core.security as security_module
import app.core.settings as settings_module
import app.services.identity as identity_module
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


def test_identity_enroll_verify(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))
    operator = _token(client, "operator", "operator")
    viewer = _token(client, "viewer", "viewer")

    payload = {
        "profile_id": "feyza",
        "device": {"hostname": "nasri-pi", "os_name": "linux", "machine_id": "abc-123"},
        "biometric_sample": "finger-sample-1",
    }
    enroll = client.post("/identity/enroll", json=payload, headers={"X-Session-Token": operator})
    assert enroll.status_code == 204

    verify = client.post("/identity/verify", json=payload, headers={"X-Session-Token": viewer})
    assert verify.status_code == 200
    assert verify.json()["verified"] is True


def test_identity_verify_fails_for_different_sample(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))
    operator = _token(client, "operator", "operator")
    payload = {
        "profile_id": "feyza",
        "device": {"hostname": "nasri-pi", "os_name": "linux", "machine_id": "abc-123"},
        "biometric_sample": "sample-a",
    }
    client.post("/identity/enroll", json=payload, headers={"X-Session-Token": operator})
    payload["biometric_sample"] = "sample-b"
    verify = client.post("/identity/verify", json=payload, headers={"X-Session-Token": operator})
    assert verify.status_code == 200
    assert verify.json()["verified"] is False

