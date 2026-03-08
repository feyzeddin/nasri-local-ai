from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest

import app.services.dependency_auditor as da_module


class _Settings:
    dependency_auditor_enabled = True
    dependency_auditor_max_output_chars = 6000


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(da_module, "get_redis", lambda: fake)
    monkeypatch.setattr(da_module, "get_settings", lambda: _Settings())
    return fake


@pytest.mark.asyncio
async def test_run_dependency_scan_and_status(monkeypatch):
    monkeypatch.setattr(
        da_module,
        "_scan_sync",
        lambda: (
            [
                {
                    "ecosystem": "python",
                    "package": "fastapi",
                    "current_version": "0.1",
                    "latest_version": "0.2",
                    "severity": "medium",
                    "detail": "outdated",
                }
            ],
            "raw",
        ),
    )
    out = await da_module.run_dependency_scan()
    assert out["ok"] is True
    assert out["issue_count"] == 1

    status = await da_module.get_dependency_status()
    assert status["enabled"] is True
    assert status["last_scan"]["scan_id"] == out["scan_id"]

