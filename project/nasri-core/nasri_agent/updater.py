import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

from .config import install_dir, local_version, state_file


def _run(args: list[str], cwd: Path | None = None) -> tuple[int, str]:
    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output.strip()


def _update_state(**kwargs: str) -> None:
    path = state_file()
    current: dict[str, str] = {}
    if path.exists():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            current = {}
    current.update(kwargs)
    current["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")


def maybe_update() -> bool:
    repo = install_dir()
    if not (repo / ".git").exists():
        _update_state(last_update_result="skip:no-git-repo")
        return False

    rc, _ = _run(["git", "fetch", "origin", "main"], cwd=repo)
    if rc != 0:
        _update_state(last_update_result="error:fetch-failed")
        return False

    rc_local, local_head = _run(["git", "rev-parse", "HEAD"], cwd=repo)
    rc_remote, remote_head = _run(["git", "rev-parse", "origin/main"], cwd=repo)
    if rc_local != 0 or rc_remote != 0:
        _update_state(last_update_result="error:rev-parse-failed")
        return False

    if local_head.strip() == remote_head.strip():
        _update_state(last_update_result="ok:already-latest", installed_version=local_version())
        return False

    rc_pull, pull_out = _run(["git", "pull", "--ff-only", "origin", "main"], cwd=repo)
    if rc_pull != 0:
        _update_state(last_update_result=f"error:pull-failed:{pull_out[:120]}")
        return False

    rc_pip, pip_out = _run(
        [sys.executable, "-m", "pip", "install", "-e", "project/nasri-core"],
        cwd=repo,
    )
    if rc_pip != 0:
        _update_state(last_update_result=f"error:pip-install-failed:{pip_out[:120]}")
        return False

    _update_state(last_update_result="ok:updated", installed_version=local_version())
    return True


def should_check_update(last_checked_iso: str | None, interval_hours: int = 24) -> bool:
    if not last_checked_iso:
        return True
    try:
        last_checked = dt.datetime.fromisoformat(last_checked_iso)
    except ValueError:
        return True
    now = dt.datetime.now(dt.timezone.utc)
    return (now - last_checked) >= dt.timedelta(hours=interval_hours)


def remote_version_hint() -> str:
    explicit = os.getenv("NASRI_REMOTE_VERSION")
    if explicit:
        return explicit
    return "origin/main"
