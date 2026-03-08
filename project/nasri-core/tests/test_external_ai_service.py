from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest

import app.services.external_ai as external_ai_module
from app.services.external_ai import ExternalAIRateLimitError


class _Settings:
    external_ai_anonymize_enabled = True
    groq_api_key = "groq-key"
    groq_api_url = "https://api.groq.com/openai/v1/chat/completions"
    groq_model = "llama-3.1-8b-instant"
    groq_rpm = 60
    groq_cost_input_per_1k = 0.1
    groq_cost_output_per_1k = 0.2
    gemini_api_key = "gemini-key"
    gemini_api_url = "https://generativelanguage.googleapis.com/v1beta/models"
    gemini_model = "gemini-1.5-flash"
    gemini_rpm = 30
    gemini_cost_input_per_1k = 0.0
    gemini_cost_output_per_1k = 0.0
    openrouter_api_key = "or-key"
    openrouter_api_url = "https://openrouter.ai/api/v1/chat/completions"
    openrouter_model = "openai/gpt-4o-mini"
    openrouter_rpm = 30
    openrouter_cost_input_per_1k = 0.0
    openrouter_cost_output_per_1k = 0.0


@pytest.fixture
def fake_redis(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(external_ai_module, "get_redis", lambda: fake)
    return fake


@pytest.mark.asyncio
async def test_send_chat_anonymizes_and_tracks_cost(monkeypatch, fake_redis):
    monkeypatch.setattr(external_ai_module, "get_settings", lambda: _Settings())

    async def _fake_call(**_kwargs):
        return "yanit", 1000, 500, "llama-3.1-8b-instant"

    monkeypatch.setattr(external_ai_module, "_call_openai_compatible", _fake_call)

    result = await external_ai_module.send_chat(
        provider="groq",
        prompt="Bana test@acme.com adresine ve +90 555 111 2233 numarasına yaz.",
    )
    assert result.provider == "groq"
    assert result.anonymized is True
    assert result.cost_usd == 0.2

    keys = await fake_redis.keys("external_ai:cost:groq:*")
    assert keys
    requests = await fake_redis.hget(keys[0], "requests")
    assert int(requests) == 1


@pytest.mark.asyncio
async def test_send_chat_enforces_rate_limit(monkeypatch, fake_redis):
    s = _Settings()
    s.groq_rpm = 1
    monkeypatch.setattr(external_ai_module, "get_settings", lambda: s)

    async def _fake_call(**_kwargs):
        return "yanit", 10, 5, "llama-3.1-8b-instant"

    monkeypatch.setattr(external_ai_module, "_call_openai_compatible", _fake_call)

    await external_ai_module.send_chat(provider="groq", prompt="ilk istek")
    with pytest.raises(ExternalAIRateLimitError):
        await external_ai_module.send_chat(provider="groq", prompt="ikinci istek")
