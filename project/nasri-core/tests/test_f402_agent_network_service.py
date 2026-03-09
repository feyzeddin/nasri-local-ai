from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest

import app.services.agent_network as an_module


class _Settings:
    agent_network_enabled = True
    agent_network_max_agents = 6


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(an_module, "get_redis", lambda: fake)
    monkeypatch.setattr(an_module, "get_settings", lambda: _Settings())
    monkeypatch.setattr(an_module, "run_planner", lambda goal, profile_id=None: (True, f"plan:{goal}", []))
    monkeypatch.setattr(an_module, "recall_memory", lambda profile_id, q, top_k=3: [{"text": "alışkanlık"}])
    return fake


@pytest.mark.asyncio
async def test_run_agent_network_and_list():
    out = await an_module.run_agent_network(
        goal="yarın için plan yap",
        profile_id="feyza",
        agents=["planner", "memory", "risk"],
        parallel=True,
    )
    assert out["completed"] is True
    assert len(out["results"]) == 3

    one = await an_module.get_run(out["run_id"])
    assert one is not None
    assert one["run_id"] == out["run_id"]

    rows = await an_module.list_runs(limit=10)
    assert len(rows) == 1

