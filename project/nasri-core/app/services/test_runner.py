from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import uuid

from app.core.redis import get_redis
from app.core.settings import get_settings

_TEST_RUNNER_PREFIX = "test_runner"
_LAST_KEY = f"{_TEST_RUNNER_PREFIX}:last"
_HISTORY_KEY = f"{_TEST_RUNNER_PREFIX}:history"


class TestRunnerError(Exception):
    pass


def _app_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _limit_output(text: str) -> str:
    limit = max(256, get_settings().test_runner_max_output_chars)
    clean = text.strip()
    if len(clean) <= limit:
        return clean
    return clean[:limit] + "\n...[truncated]"


def _build_command(target: str, keyword: str | None) -> list[str]:
    cmd = ["pytest", "-q", target]
    if keyword:
        cmd.extend(["-k", keyword])
    return cmd


def _run_sync(command: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        command,
        cwd=str(_app_root()),
        capture_output=True,
        text=True,
        check=False,
    )
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return int(proc.returncode), _limit_output(output)


async def _store_result(payload: dict) -> None:
    r = get_redis()
    data = json.dumps(payload, ensure_ascii=False)
    pipe = r.pipeline()
    pipe.set(_LAST_KEY, data)
    pipe.lpush(_HISTORY_KEY, data)
    pipe.ltrim(_HISTORY_KEY, 0, 19)
    await pipe.execute()


def _validate_enabled() -> None:
    if not get_settings().test_runner_enabled:
        raise TestRunnerError("Test runner devre dışı.")


def _normalize_target(target: str | None) -> str:
    default_target = get_settings().test_runner_default_target or "tests"
    normalized = (target or default_target).strip()
    if not normalized:
        raise TestRunnerError("Geçersiz test hedefi.")
    if ".." in normalized:
        raise TestRunnerError("Target path traversal içeremez.")
    return normalized


def _decode(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


async def run_tests(*, target: str | None = None, keyword: str | None = None) -> dict:
    _validate_enabled()
    normalized_target = _normalize_target(target)
    started_at = datetime.now(timezone.utc)
    run_id = str(uuid.uuid4())
    command = _build_command(normalized_target, keyword)

    return_code, output = await asyncio.to_thread(_run_sync, command)
    duration_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
    payload = {
        "run_id": run_id,
        "command": command,
        "target": normalized_target,
        "keyword": keyword,
        "return_code": return_code,
        "ok": return_code == 0,
        "duration_ms": duration_ms,
        "output": output,
        "started_at": started_at.isoformat(),
    }
    await _store_result(payload)
    return payload


async def get_last_result() -> dict | None:
    _validate_enabled()
    r = get_redis()
    raw = await r.get(_LAST_KEY)
    return _decode(raw)


async def list_history(limit: int = 10) -> list[dict]:
    _validate_enabled()
    clamped = max(1, min(50, int(limit)))
    r = get_redis()
    raw_items = await r.lrange(_HISTORY_KEY, 0, clamped - 1)
    out: list[dict] = []
    for raw in raw_items:
        item = _decode(raw)
        if item:
            out.append(item)
    return out

