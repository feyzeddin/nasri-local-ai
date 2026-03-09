from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest

import app.services.beta_program as bp_module


class _Settings:
    beta_program_enabled = True


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(bp_module, "get_redis", lambda: fake)
    monkeypatch.setattr(bp_module, "get_settings", lambda: _Settings())
    return fake


@pytest.mark.asyncio
async def test_candidate_and_feedback_flow():
    candidate = await bp_module.create_candidate(
        name="Feyza",
        email="feyza@example.com",
        nda_accepted=True,
        note="beta",
    )
    assert candidate["status"] == "approved"

    candidates = await bp_module.list_candidates()
    assert len(candidates) == 1
    assert candidates[0]["email"] == "feyza@example.com"

    feedback = await bp_module.create_feedback(
        candidate_id=candidate["candidate_id"],
        score=5,
        text="Harika",
    )
    assert feedback["score"] == 5
    listed = await bp_module.list_feedback(limit=10)
    assert len(listed) == 1

