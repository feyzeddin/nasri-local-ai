from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest

import app.services.test_runner as tr_module


class _Settings:
    test_runner_enabled = True
    test_runner_default_target = "tests"
    test_runner_max_output_chars = 6000


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(tr_module, "get_redis", lambda: fake)
    monkeypatch.setattr(tr_module, "get_settings", lambda: _Settings())
    return fake


@pytest.mark.asyncio
async def test_run_tests_and_history(monkeypatch):
    monkeypatch.setattr(tr_module, "_run_sync", lambda _cmd: (0, "2 passed"))
    out = await tr_module.run_tests(target="tests", keyword="chat")
    assert out["ok"] is True
    assert out["return_code"] == 0
    assert out["keyword"] == "chat"

    last = await tr_module.get_last_result()
    assert last is not None
    assert last["run_id"] == out["run_id"]

    history = await tr_module.list_history(limit=5)
    assert len(history) == 1
    assert history[0]["run_id"] == out["run_id"]


@pytest.mark.asyncio
async def test_run_tests_rejects_path_traversal():
    with pytest.raises(tr_module.TestRunnerError, match="path traversal"):
        await tr_module.run_tests(target="../secret")

