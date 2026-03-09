from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest

import app.services.messaging_bridge as m


class _Settings:
    system_prompt = None
    nasri_version = "0.2.0"
    telegram_bot_token = ""
    whatsapp_access_token = ""
    whatsapp_phone_number_id = ""


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(m, "get_redis", lambda: fake)
    monkeypatch.setattr(m, "get_settings", lambda: _Settings())
    return fake


@pytest.mark.asyncio
async def test_ask_nasri_uses_model_router(monkeypatch):
    await m.confirm_pairing(
        (
            await m.start_pairing(
                channel="telegram",
                external_user_id="u1",
                chat_id="c1",
            )
        )["pair_code"]
    )

    class _Result:
        reply = "tamam"
        used_tier = "local"
        attempts = []

    async def _fake_route_chat(*, prompt: str, system_prompt: str | None = None):
        assert "Kullanıcı: merhaba" in prompt
        return _Result()

    monkeypatch.setattr(m, "route_chat", _fake_route_chat)
    out = await m.ask_nasri("telegram", "u1", "merhaba")
    assert out == "tamam"
