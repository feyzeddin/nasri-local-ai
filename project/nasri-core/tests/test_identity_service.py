from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest

import app.core.redis as redis_module
import app.services.identity as id_module
from app.schemas.identity import DeviceInfo


class _Settings:
    device_fingerprint_salt = "device-salt"
    biometric_salt = "bio-salt"


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_module, "get_redis", lambda: fake)
    monkeypatch.setattr(id_module, "get_redis", lambda: fake)
    monkeypatch.setattr(id_module, "get_settings", lambda: _Settings())
    return fake


def _device() -> DeviceInfo:
    return DeviceInfo(hostname="nasri-pi", os_name="linux", machine_id="abc-123")


@pytest.mark.asyncio
async def test_enroll_and_verify_success():
    await id_module.enroll_identity("feyza", _device(), "fingerprint-vector-1")
    result = await id_module.verify_identity("feyza", _device(), "fingerprint-vector-1")
    assert result.verified is True
    assert result.device_match is True
    assert result.biometric_match is True


@pytest.mark.asyncio
async def test_verify_fails_when_biometric_different():
    await id_module.enroll_identity("feyza", _device(), "sample-a")
    result = await id_module.verify_identity("feyza", _device(), "sample-b")
    assert result.verified is False
    assert result.device_match is True
    assert result.biometric_match is False

