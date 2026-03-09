from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest

import app.services.anomaly as a_module


class _Settings:
    anomaly_enabled = True
    anomaly_network_bytes_threshold = 100
    anomaly_network_conn_threshold_per_minute = 3
    anomaly_file_burst_threshold_per_minute = 3
    anomaly_sensitive_paths = "/etc,C:\\Windows"


@pytest.fixture
def fake_redis(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(a_module, "get_redis", lambda: fake)
    monkeypatch.setattr(a_module, "get_settings", lambda: _Settings())
    return fake


@pytest.mark.asyncio
async def test_network_bytes_anomaly(fake_redis):
    result, alert_id = await a_module.ingest_event(
        event_type="network",
        actor="sensor-1",
        source_ip="192.168.1.10",
        destination_ip="8.8.8.8",
        bytes_in=60,
        bytes_out=60,
    )
    assert result.anomaly is True
    assert result.severity == "high"
    assert alert_id is not None


@pytest.mark.asyncio
async def test_file_sensitive_anomaly(fake_redis):
    result, alert_id = await a_module.ingest_event(
        event_type="file_access",
        actor="proc-a",
        path="/etc/passwd",
        operation="delete",
    )
    assert result.anomaly is True
    assert result.severity == "high"
    assert alert_id is not None


@pytest.mark.asyncio
async def test_list_alerts(fake_redis):
    await a_module.ingest_event(
        event_type="network",
        actor="sensor-1",
        bytes_in=120,
        bytes_out=0,
    )
    alerts = await a_module.list_alerts(limit=10)
    assert len(alerts) >= 1
