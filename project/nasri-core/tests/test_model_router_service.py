from __future__ import annotations

import pytest

import app.services.model_router as router_module
from app.services.model_router import ModelRouterError


class _Settings:
    def __init__(self) -> None:
        self.ollama_url = "http://localhost:11434"
        self.model_name = "llama3"
        self.model_router_tier_order = "local,free,paid"
        self.model_router_free_enabled = True
        self.model_router_free_api_url = "https://free.example.com/chat/completions"
        self.model_router_free_api_key = ""
        self.model_router_free_model = "free-model"
        self.model_router_free_provider = ""
        self.model_router_paid_enabled = True
        self.model_router_paid_api_url = "https://paid.example.com/chat/completions"
        self.model_router_paid_api_key = "paid-key"
        self.model_router_paid_model = "paid-model"
        self.model_router_paid_provider = ""


@pytest.mark.asyncio
async def test_route_chat_uses_local_first(monkeypatch):
    monkeypatch.setattr(router_module, "get_settings", lambda: _Settings())

    async def _local(_messages):
        return "yerel yanit"

    monkeypatch.setattr(router_module, "_chat_local", _local)

    result = await router_module.route_chat(prompt="Merhaba")
    assert result.reply == "yerel yanit"
    assert result.used_tier == "local"
    assert result.attempts[0].tier == "local"
    assert result.attempts[0].status == "ok"


@pytest.mark.asyncio
async def test_route_chat_falls_back_to_free(monkeypatch):
    monkeypatch.setattr(router_module, "get_settings", lambda: _Settings())

    async def _local(_messages):
        raise ModelRouterError("local down")

    async def _remote(**_kwargs):
        return "free yanit"

    monkeypatch.setattr(router_module, "_chat_local", _local)
    monkeypatch.setattr(router_module, "_chat_remote", _remote)

    result = await router_module.route_chat(prompt="Merhaba")
    assert result.reply == "free yanit"
    assert result.used_tier == "free"
    assert [a.tier for a in result.attempts] == ["local", "free"]
    assert result.attempts[0].status == "failed"
    assert result.attempts[1].status == "ok"


@pytest.mark.asyncio
async def test_route_chat_raises_when_all_layers_unavailable(monkeypatch):
    s = _Settings()
    s.model_router_free_enabled = False
    s.model_router_paid_enabled = False
    monkeypatch.setattr(router_module, "get_settings", lambda: s)

    async def _local(_messages):
        raise ModelRouterError("local down")

    monkeypatch.setattr(router_module, "_chat_local", _local)

    with pytest.raises(ModelRouterError, match="Uygun model katmanı bulunamadı"):
        await router_module.route_chat(prompt="Merhaba")


@pytest.mark.asyncio
async def test_route_chat_respects_preferred_tier(monkeypatch):
    settings = _Settings()
    settings.model_router_free_provider = "groq"
    monkeypatch.setattr(router_module, "get_settings", lambda: settings)
    calls: list[str] = []

    async def _local(_messages):
        calls.append("local")
        return "local"

    async def _send_chat(**kwargs):
        calls.append(str(kwargs.get("provider")))

        class _R:
            reply = "free"

        return _R()

    monkeypatch.setattr(router_module, "_chat_local", _local)
    monkeypatch.setattr(router_module, "send_chat", _send_chat)

    result = await router_module.route_chat(prompt="Merhaba", preferred_tier="free")
    assert result.used_tier == "free"
    assert calls == ["groq"]
