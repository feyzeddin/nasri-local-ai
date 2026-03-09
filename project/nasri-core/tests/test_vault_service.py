from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest

import app.core.redis as redis_module
import app.services.vault as vault_module


class _Settings:
    vault_master_key = "super-secret-master-key"
    vault_key_id = "v1"

    @staticmethod
    def vault_key_bytes() -> bytes:
        import hashlib

        return hashlib.sha256(_Settings.vault_master_key.encode("utf-8")).digest()


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_module, "get_redis", lambda: fake)
    monkeypatch.setattr(vault_module, "get_redis", lambda: fake)
    monkeypatch.setattr(vault_module, "get_settings", lambda: _Settings())
    return fake


@pytest.mark.asyncio
async def test_vault_roundtrip():
    key_id = await vault_module.set_secret("api_token", "abc123")
    assert key_id == "v1"
    value, out_key_id = await vault_module.get_secret("api_token")
    assert value == "abc123"
    assert out_key_id == "v1"


@pytest.mark.asyncio
async def test_vault_delete():
    await vault_module.set_secret("x", "y")
    await vault_module.delete_secret("x")
    with pytest.raises(vault_module.VaultError):
        await vault_module.get_secret("x")

