from __future__ import annotations

import json

import fakeredis.aioredis as fakeredis
import pytest

import app.services.international as i_module


class _Settings:
    supported_locales = ["tr", "en", "de"]
    default_locale = "tr"


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(i_module, "get_redis", lambda: fake)
    monkeypatch.setattr(i_module, "get_settings", lambda: _Settings())
    return fake


@pytest.mark.asyncio
async def test_locale_export_erase_flow(setup):
    await i_module.set_locale("feyza", "en")
    loc = await i_module.get_locale("feyza")
    assert loc["locale"] == "en"

    await setup.set("identity:profile:feyza", json.dumps({"profile_id": "feyza"}))
    await setup.rpush("conversation:feyza", "m1")
    await setup.sadd("finetune:datasets", "ds1")
    await setup.set("finetune:dataset:ds1", json.dumps({"dataset_id": "ds1", "profile_id": "feyza"}))
    await setup.sadd("beta:candidates", "c1")
    await setup.set("beta:candidate:c1", json.dumps({"candidate_id": "c1", "email": "feyza@example.com"}))

    exported = await i_module.export_profile_data("feyza", "feyza@example.com")
    assert exported["profile_id"] == "feyza"
    assert len(exported["data"]["fine_tuning_datasets"]) == 1

    deleted = await i_module.erase_profile_data("feyza", "feyza@example.com")
    assert deleted >= 1

