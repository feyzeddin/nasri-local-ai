from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import PurePath
import uuid

from app.core.redis import get_redis
from app.core.settings import get_settings


class AnomalyError(Exception):
    pass


@dataclass
class DetectionResult:
    anomaly: bool
    severity: str | None = None
    reason: str | None = None


_ALERT_KEY = "anomaly:alerts"
_MAX_ALERTS = 500


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _sensitive_paths() -> list[str]:
    raw = get_settings().anomaly_sensitive_paths
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


def _is_sensitive(path: str) -> bool:
    p = str(PurePath(path)).lower()
    for root in _sensitive_paths():
        r = root.lower()
        if p == r or p.startswith(r + "/") or p.startswith(r + "\\"):
            return True
    return False


async def _rate_count(kind: str, key_part: str) -> int:
    now_bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    key = f"anomaly:rate:{kind}:{key_part}:{now_bucket}"
    r = get_redis()
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, 120)
    return int(count)


def _detect_network(bytes_in: int, bytes_out: int, burst_count: int) -> DetectionResult:
    s = get_settings()
    total = bytes_in + bytes_out
    if total >= s.anomaly_network_bytes_threshold:
        return DetectionResult(
            anomaly=True,
            severity="high",
            reason=f"Ağ trafiği eşiği aşıldı ({total} byte).",
        )
    if burst_count > s.anomaly_network_conn_threshold_per_minute:
        return DetectionResult(
            anomaly=True,
            severity="medium",
            reason=f"Dakikalık bağlantı eşiği aşıldı ({burst_count}/dk).",
        )
    return DetectionResult(anomaly=False)


def _detect_file(path: str | None, operation: str | None, burst_count: int) -> DetectionResult:
    s = get_settings()
    op = (operation or "").strip().lower()
    if burst_count > s.anomaly_file_burst_threshold_per_minute:
        return DetectionResult(
            anomaly=True,
            severity="medium",
            reason=f"Dakikalık dosya erişim eşiği aşıldı ({burst_count}/dk).",
        )
    if path and _is_sensitive(path) and op in {"write", "delete", "chmod", "chown"}:
        return DetectionResult(
            anomaly=True,
            severity="high",
            reason=f"Hassas path üzerinde şüpheli işlem: {op}",
        )
    return DetectionResult(anomaly=False)


async def _store_alert(event_type: str, actor: str, result: DetectionResult, details: dict) -> str:
    if not result.anomaly or not result.reason or not result.severity:
        raise AnomalyError("Uyarı oluşturulamaz.")
    alert_id = str(uuid.uuid4())
    payload = {
        "alert_id": alert_id,
        "created_at": _now_ts(),
        "event_type": event_type,
        "actor": actor,
        "severity": result.severity,
        "reason": result.reason,
        "details": details,
    }
    r = get_redis()
    await r.lpush(_ALERT_KEY, json.dumps(payload, ensure_ascii=False))
    await r.ltrim(_ALERT_KEY, 0, _MAX_ALERTS - 1)
    return alert_id


async def ingest_event(
    *,
    event_type: str,
    actor: str,
    source_ip: str | None = None,
    destination_ip: str | None = None,
    bytes_in: int = 0,
    bytes_out: int = 0,
    path: str | None = None,
    operation: str | None = None,
) -> tuple[DetectionResult, str | None]:
    s = get_settings()
    if not s.anomaly_enabled:
        raise AnomalyError("Anomaly detector devre dışı.")

    event = event_type.strip().lower()
    who = actor.strip()
    if event not in {"network", "file_access"}:
        raise AnomalyError("Desteklenmeyen event_type.")
    if not who:
        raise AnomalyError("actor boş olamaz.")

    if event == "network":
        burst = await _rate_count("network", who)
        result = _detect_network(bytes_in=bytes_in, bytes_out=bytes_out, burst_count=burst)
        details = {
            "source_ip": source_ip,
            "destination_ip": destination_ip,
            "bytes_in": bytes_in,
            "bytes_out": bytes_out,
            "burst_count": burst,
        }
    else:
        burst = await _rate_count("file", who)
        result = _detect_file(path=path, operation=operation, burst_count=burst)
        details = {
            "path": path,
            "operation": operation,
            "burst_count": burst,
        }

    alert_id = None
    if result.anomaly:
        alert_id = await _store_alert(event, who, result, details)
    return result, alert_id


async def list_alerts(limit: int = 50) -> list[dict]:
    r = get_redis()
    raw = await r.lrange(_ALERT_KEY, 0, max(0, limit - 1))
    alerts: list[dict] = []
    for item in raw:
        try:
            alerts.append(json.loads(item))
        except json.JSONDecodeError:
            continue
    return alerts


def detector_status() -> dict:
    s = get_settings()
    return {
        "enabled": s.anomaly_enabled,
        "network_bytes_threshold": s.anomaly_network_bytes_threshold,
        "network_conn_threshold_per_minute": s.anomaly_network_conn_threshold_per_minute,
        "file_burst_threshold_per_minute": s.anomaly_file_burst_threshold_per_minute,
    }
