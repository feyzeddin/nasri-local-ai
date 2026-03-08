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
        self.whisper_cpp_binary = "whisper"
        self.whisper_cpp_model = "model.bin"
        self.whisper_cpp_language = "tr"
        self.whisper_cpp_timeout_seconds = 120


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_module, "get_redis", lambda: fake)
    monkeypatch.setattr(security_module, "get_redis", lambda: fake)
    return fake


def _client(monkeypatch) -> TestClient:
    settings = _Settings()
    monkeypatch.setattr(settings_module, "get_settings", lambda: settings)
    monkeypatch.setattr(security_module, "get_settings", lambda: settings)
    import app.api.files as files_module
    import app.api.speech as speech_module
    import app.main as main_module

    monkeypatch.setattr(files_module, "get_settings", lambda: settings)
    monkeypatch.setattr(speech_module, "get_settings", lambda: settings)
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    app = main_module._create_app()
    return TestClient(app)


def test_transcribe_success(monkeypatch):
    client = _client(monkeypatch)
    import app.api.speech as speech_module

    monkeypatch.setattr(speech_module, "transcribe_audio_bytes", lambda *_args, **_kwargs: "merhaba dunya")
    resp = client.post(
        "/speech/transcribe",
        files={"audio": ("sample.wav", b"RIFF....WAVE", "audio/wav")},
    )
    assert resp.status_code == 200
    assert resp.json()["text"] == "merhaba dunya"
    assert resp.json()["language"] == "tr"


def test_transcribe_rejects_non_audio(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post(
        "/speech/transcribe",
        files={"audio": ("sample.txt", b"abc", "text/plain")},
    )
    assert resp.status_code == 400


def test_synthesize_success(monkeypatch):
    client = _client(monkeypatch)
    import app.api.speech as speech_module

    monkeypatch.setattr(speech_module, "synthesize_speech", lambda *_args, **_kwargs: b"RIFFdemoWAVE")
    resp = client.post("/speech/synthesize", json={"text": "Selam"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("audio/wav")
    assert resp.content.startswith(b"RIFF")


def test_synthesize_rejects_empty_text(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post("/speech/synthesize", json={"text": "   "})
    assert resp.status_code == 400

