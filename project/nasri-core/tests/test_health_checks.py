from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import app.core.health as health_module


@pytest.mark.asyncio
async def test_check_redis_ok(monkeypatch):
    fake = AsyncMock()
    fake.ping = AsyncMock(return_value=True)
    monkeypatch.setattr(health_module, "get_redis", lambda: fake)
    ok, detail = await health_module.check_redis()
    assert ok is True
    assert detail == "ok"


@pytest.mark.asyncio
async def test_check_redis_error(monkeypatch):
    fake = AsyncMock()
    fake.ping = AsyncMock(side_effect=RuntimeError("down"))
    monkeypatch.setattr(health_module, "get_redis", lambda: fake)
    ok, detail = await health_module.check_redis()
    assert ok is False
    assert detail.startswith("error:")


@pytest.mark.asyncio
async def test_build_readiness_degraded_if_any_dependency_down(monkeypatch):
    async def _redis():
        return True, "ok"

    async def _ollama():
        return False, "error:timeout"

    monkeypatch.setattr(health_module, "check_redis", _redis)
    monkeypatch.setattr(health_module, "check_ollama", _ollama)
    result = await health_module.build_readiness()
    assert result["status"] == "degraded"
    assert result["checks"]["ollama"]["ok"] is False

