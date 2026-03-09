from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import subprocess
import time

from app.core.redis import get_redis
from app.core.settings import get_settings


class MaintenanceError(Exception):
    pass


_LAST_RUN_KEY = "maintenance:last_run_at"
_LAST_RESULT_KEY = "maintenance:last_result"


@dataclass
class MaintenanceConfig:
    enabled: bool
    interval_hours: int
    log_dirs: list[str]
    retention_days: int
    auto_update_enabled: bool
    update_command: str
    disk_paths: list[str]


def _cfg() -> MaintenanceConfig:
    s = get_settings()
    log_dirs_raw = getattr(s, "maintenance_log_dirs", "logs,tmp")
    disk_paths_raw = getattr(s, "maintenance_disk_paths", ".")
    return MaintenanceConfig(
        enabled=bool(getattr(s, "maintenance_enabled", True)),
        interval_hours=max(1, int(getattr(s, "maintenance_interval_hours", 24))),
        log_dirs=[x.strip() for x in str(log_dirs_raw).split(",") if x.strip()],
        retention_days=max(1, int(getattr(s, "maintenance_log_retention_days", 14))),
        auto_update_enabled=bool(
            getattr(s, "maintenance_auto_update_enabled", False)
        ),
        update_command=str(getattr(s, "maintenance_update_command", "")).strip(),
        disk_paths=[x.strip() for x in str(disk_paths_raw).split(",") if x.strip()],
    )


def _default_update_command() -> str:
    if os.name == "nt":
        return "winget upgrade --all --silent"
    return "sudo apt-get update && sudo apt-get -y upgrade"


def _disk_report(paths: list[str]) -> dict[str, dict[str, float]]:
    report: dict[str, dict[str, float]] = {}
    for p in paths:
        target = Path(p).expanduser()
        if not target.exists():
            report[str(target)] = {"exists": 0.0, "used_gb": 0.0, "free_gb": 0.0}
            continue
        usage = shutil.disk_usage(target)
        report[str(target)] = {
            "exists": 1.0,
            "used_gb": round(usage.used / (1024**3), 3),
            "free_gb": round(usage.free / (1024**3), 3),
        }
    return report


def _cleanup_logs(log_dirs: list[str], retention_days: int) -> dict[str, int]:
    now = time.time()
    max_age_seconds = retention_days * 24 * 60 * 60
    deleted_files = 0
    scanned_files = 0

    for d in log_dirs:
        root = Path(d).expanduser()
        if not root.exists() or not root.is_dir():
            continue
        for file in root.rglob("*"):
            if not file.is_file():
                continue
            scanned_files += 1
            try:
                age = now - file.stat().st_mtime
            except OSError:
                continue
            if age >= max_age_seconds:
                try:
                    file.unlink(missing_ok=True)
                    deleted_files += 1
                except OSError:
                    continue
    return {"scanned_files": scanned_files, "deleted_files": deleted_files}


def _run_updates(enabled: bool, cmd: str) -> dict[str, str | int]:
    if not enabled:
        return {"status": "skipped", "exit_code": 0, "detail": "auto update kapalı"}

    command = cmd or _default_update_command()
    try:
        proc = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            shell=True,
            timeout=900,
        )
    except Exception as exc:
        return {"status": "failed", "exit_code": 1, "detail": str(exc)}

    detail = (proc.stdout or proc.stderr or "").strip()
    if len(detail) > 500:
        detail = detail[:500] + "..."
    return {
        "status": "ok" if proc.returncode == 0 else "failed",
        "exit_code": int(proc.returncode),
        "detail": detail or "no output",
    }


async def get_maintenance_status() -> dict:
    cfg = _cfg()
    r = get_redis()
    raw_last_run = await r.get(_LAST_RUN_KEY)
    raw_last_result = await r.get(_LAST_RESULT_KEY)
    last_run_at = int(raw_last_run) if raw_last_run else None

    due = True
    if last_run_at is not None:
        due = (int(time.time()) - last_run_at) >= (cfg.interval_hours * 3600)
    return {
        "enabled": cfg.enabled,
        "interval_hours": cfg.interval_hours,
        "last_run_at": last_run_at,
        "last_result": raw_last_result,
        "due": due,
    }


async def run_maintenance(trigger: str = "manual") -> dict:
    cfg = _cfg()
    if not cfg.enabled:
        raise MaintenanceError("Maintenance devre dışı.")

    ran_at = int(datetime.now(timezone.utc).timestamp())
    disk = _disk_report(cfg.disk_paths)
    logs = _cleanup_logs(cfg.log_dirs, cfg.retention_days)
    updates = _run_updates(cfg.auto_update_enabled, cfg.update_command)
    ok = updates.get("status") in {"ok", "skipped"}

    result = {
        "trigger": trigger,
        "ran_at": ran_at,
        "disk": disk,
        "logs": logs,
        "updates": updates,
        "ok": bool(ok),
    }
    r = get_redis()
    await r.set(_LAST_RUN_KEY, str(ran_at))
    await r.set(_LAST_RESULT_KEY, str(updates.get("status", "unknown")))
    return result


async def run_maintenance_if_due(trigger: str = "schedule") -> dict | None:
    status = await get_maintenance_status()
    if not status["due"]:
        return None
    return await run_maintenance(trigger=trigger)
