from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest

import app.services.maintenance as m_module


class _Settings:
    maintenance_enabled = True
    maintenance_interval_hours = 24
    maintenance_log_dirs = "logs,tmp"
    maintenance_log_retention_days = 1
    maintenance_auto_update_enabled = False
    maintenance_update_command = ""
    maintenance_disk_paths = "."


@pytest.fixture
def fake_redis(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(m_module, "get_redis", lambda: fake)
    return fake


@pytest.mark.asyncio
async def test_run_maintenance_writes_status(monkeypatch, tmp_path, fake_redis):
    logs = tmp_path / "logs"
    logs.mkdir()
    old_file = logs / "old.log"
    old_file.write_text("x", encoding="utf-8")
    monkeypatch.setattr(m_module, "time", __import__("time"))
    old_ts = m_module.time.time() - (2 * 24 * 60 * 60)
    old_file.touch()
    import os

    os.utime(old_file, (old_ts, old_ts))

    s = _Settings()
    s.maintenance_log_dirs = str(logs)
    s.maintenance_disk_paths = str(tmp_path)
    monkeypatch.setattr(m_module, "get_settings", lambda: s)

    result = await m_module.run_maintenance(trigger="manual")
    assert result["ok"] is True
    assert result["logs"]["deleted_files"] >= 1

    status = await m_module.get_maintenance_status()
    assert status["last_run_at"] is not None
    assert status["last_result"] == "skipped"


@pytest.mark.asyncio
async def test_run_if_due_skips_when_recent(monkeypatch, fake_redis):
    monkeypatch.setattr(m_module, "get_settings", lambda: _Settings())
    now = int(m_module.time.time())
    await fake_redis.set("maintenance:last_run_at", str(now))
    out = await m_module.run_maintenance_if_due()
    assert out is None
