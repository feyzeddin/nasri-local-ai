from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import uuid
from typing import Any

from app.core.redis import get_redis
from app.core.settings import get_settings

_PREFIX = "dependency_auditor"
_LAST_KEY = f"{_PREFIX}:last"


class DependencyAuditorError(Exception):
    pass


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _limit_output(text: str) -> str:
    limit = max(256, get_settings().dependency_auditor_max_output_chars)
    clean = text.strip()
    if len(clean) <= limit:
        return clean
    return clean[:limit] + "\n...[truncated]"


def _run(args: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return int(proc.returncode), output


def _parse_pip_outdated_json(raw: str) -> list[dict[str, Any]]:
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    issues: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        issues.append(
            {
                "ecosystem": "python",
                "package": str(item.get("name", "")),
                "current_version": str(item.get("version", "")),
                "latest_version": str(item.get("latest_version", "")),
                "severity": "medium",
                "detail": "outdated",
            }
        )
    return issues


def _parse_npm_audit_json(raw: str) -> list[dict[str, Any]]:
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    vulnerabilities = data.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        return []
    issues: list[dict[str, Any]] = []
    for package, info in vulnerabilities.items():
        if not isinstance(info, dict):
            continue
        severity = str(info.get("severity", "unknown"))
        fix = info.get("fixAvailable")
        detail = "fix available" if fix else "no fix info"
        issues.append(
            {
                "ecosystem": "npm",
                "package": str(package),
                "current_version": str(info.get("range", "")),
                "latest_version": "-",
                "severity": severity,
                "detail": detail,
            }
        )
    return issues


def _scan_sync() -> tuple[list[dict[str, Any]], str]:
    root = _repo_root()
    raw_chunks: list[str] = []
    issues: list[dict[str, Any]] = []

    py_cwd = root / "nasri-core"
    py_rc, py_raw = _run(["python", "-m", "pip", "list", "--outdated", "--format=json"], cwd=py_cwd)
    raw_chunks.append(f"[python rc={py_rc}]\n{py_raw}")
    issues.extend(_parse_pip_outdated_json(py_raw))

    ui_cwd = root / "nasri-ui"
    npm_rc, npm_raw = _run(["npm", "audit", "--json"], cwd=ui_cwd)
    raw_chunks.append(f"[npm rc={npm_rc}]\n{npm_raw}")
    issues.extend(_parse_npm_audit_json(npm_raw))
    return issues, _limit_output("\n\n".join(raw_chunks))


def _ensure_enabled() -> None:
    if not get_settings().dependency_auditor_enabled:
        raise DependencyAuditorError("Dependency auditor devre dışı.")


async def _save_last(payload: dict[str, Any]) -> None:
    r = get_redis()
    await r.set(_LAST_KEY, json.dumps(payload, ensure_ascii=False))


def _decode(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


async def run_dependency_scan() -> dict[str, Any]:
    _ensure_enabled()
    started_at = datetime.now(timezone.utc)
    scan_id = str(uuid.uuid4())
    issues, raw_output = await asyncio.to_thread(_scan_sync)
    duration_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
    payload = {
        "scan_id": scan_id,
        "ok": True,
        "issue_count": len(issues),
        "issues": issues,
        "duration_ms": duration_ms,
        "started_at": started_at.isoformat(),
        "raw_output": raw_output,
    }
    await _save_last(payload)
    return payload


async def get_dependency_status() -> dict[str, Any]:
    _ensure_enabled()
    r = get_redis()
    raw = await r.get(_LAST_KEY)
    return {"enabled": True, "last_scan": _decode(raw)}

