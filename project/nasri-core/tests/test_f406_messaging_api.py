from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest
from fastapi.testclient import TestClient

import app.core.redis as redis_module
import app.core.security as security_module
import app.core.settings as settings_module
import app.services.identity as identity_module
import app.services.messaging_bridge as bridge_service
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
        self.nasri_version = "0.1.0"
        self.telegram_enabled = True
        self.telegram_bot_token = "x"
        self.telegram_webhook_secret = "secret"
        self.whatsapp_enabled = True
        self.whatsapp_verify_token = "verify-token"
        self.whatsapp_access_token = "wa-token"
        self.whatsapp_phone_number_id = "phone-1"
        self.enterprise_module_enabled = True
        self.enterprise_base_monthly_price = 49999.0
        self.supported_locales = ["tr", "en", "de"]
        self.default_locale = "tr"

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
    monkeypatch.setattr(bridge_service, "get_redis", lambda: fake)
    return fake


def _make_client(monkeypatch, settings: _Settings) -> TestClient:
    monkeypatch.setattr(settings_module, "get_settings", lambda: settings)
    monkeypatch.setattr(security_module, "get_settings", lambda: settings)
    monkeypatch.setattr(identity_module, "get_settings", lambda: settings)
    monkeypatch.setattr(vault_module, "get_settings", lambda: settings)
    monkeypatch.setattr(bridge_service, "get_settings", lambda: settings)
    import app.api.files as files_module
    import app.api.messaging as messaging_api
    import app.api.speech as speech_module
    import app.main as main_module

    monkeypatch.setattr(files_module, "get_settings", lambda: settings)
    monkeypatch.setattr(speech_module, "get_settings", lambda: settings)
    monkeypatch.setattr(messaging_api, "get_settings", lambda: settings)
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


def test_pairing_flow(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))
    op = _token(client, "operator", "operator")
    vw = _token(client, "viewer", "viewer")

    started = client.post(
        "/messaging/pairings/start",
        json={"channel": "telegram", "external_user_id": "1001", "chat_id": "42"},
        headers={"X-Session-Token": op},
    )
    assert started.status_code == 200
    code = started.json()["pair_code"]

    confirmed = client.post(
        "/messaging/pairings/confirm",
        json={"pair_code": code},
        headers={"X-Session-Token": op},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["channel"] == "telegram"
    assert confirmed.json()["external_user_id"] == "1001"

    owner = client.get("/messaging/pairings/owner", headers={"X-Session-Token": vw})
    assert owner.status_code == 200
    assert owner.json()["chat_id"] == "42"


def test_telegram_webhook_command_and_chat(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))
    sent: list[str] = []

    async def _fake_send(_chat_id: str, text: str) -> None:
        sent.append(text)

    async def _fake_ask(_channel: str, _external_user_id: str, _text: str) -> str:
        return "cevap"

    import app.api.messaging as messaging_api

    monkeypatch.setattr(messaging_api, "send_telegram_message", _fake_send)
    monkeypatch.setattr(messaging_api, "ask_nasri", _fake_ask)

    cmd = client.post(
        "/messaging/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        json={
            "message": {
                "chat": {"id": 55},
                "from": {"id": 9001},
                "text": "/status",
            }
        },
    )
    assert cmd.status_code == 200
    assert sent[-1] == "Selamunaleyküm ben Nasrî"

    normal = client.post(
        "/messaging/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        json={
            "message": {
                "chat": {"id": 55},
                "from": {"id": 9001},
                "text": "Merhaba",
            }
        },
    )
    assert normal.status_code == 200
    assert sent[-1] == "cevap"


def test_whatsapp_webhook_verify(monkeypatch):
    client = _make_client(monkeypatch, _Settings(rbac_enabled=True))
    ok = client.get(
        "/messaging/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=verify-token&hub.challenge=abc123"
    )
    assert ok.status_code == 200
    assert ok.text == "abc123"
