from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.redis import get_redis
from app.core.settings import get_settings


class BackupError(Exception):
    pass


_HISTORY_KEY = "backup:history"
_MAX_HISTORY = 100


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _source_paths() -> list[Path]:
    raw = get_settings().backup_source_paths
    out: list[Path] = []
    for p in raw.split(","):
        part = p.strip()
        if not part:
            continue
        out.append(Path(part).expanduser())
    return out


def _build_archive(temp_tar_path: Path, sources: list[Path]) -> None:
    with tarfile.open(temp_tar_path, "w:gz") as tf:
        for src in sources:
            if not src.exists():
                continue
            tf.add(src, arcname=src.name)


def _encrypt_file(input_path: Path, output_path: Path) -> None:
    key = get_settings().vault_key_bytes()
    aes = AESGCM(key)
    nonce = os.urandom(12)
    raw = input_path.read_bytes()
    ciphertext = aes.encrypt(nonce, raw, None)
    output_path.write_bytes(base64.b64encode(nonce + ciphertext))


def _remote_sync(local_file: Path) -> str:
    s = get_settings()
    if not s.backup_remote_target:
        return "skipped:no-target"
    if not s.backup_remote_command:
        return "skipped:no-command"

    command = s.backup_remote_command.format(
        file=str(local_file),
        target=s.backup_remote_target,
    )
    try:
        proc = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=600,
            shell=True,
        )
    except Exception as exc:
        return f"failed:{exc}"
    return "ok" if proc.returncode == 0 else f"failed:exit-{proc.returncode}"


def _prune_backups(output_dir: Path, retention_count: int) -> None:
    files = sorted(
        [f for f in output_dir.glob("backup-*") if f.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in files[retention_count:]:
        old.unlink(missing_ok=True)


async def _store_history(item: dict) -> None:
    r = get_redis()
    await r.lpush(_HISTORY_KEY, json.dumps(item, ensure_ascii=False))
    await r.ltrim(_HISTORY_KEY, 0, _MAX_HISTORY - 1)


async def run_backup(trigger: str = "manual") -> dict:
    s = get_settings()
    if not s.backup_enabled:
        raise BackupError("Backup manager devre dışı.")

    backup_id = str(uuid.uuid4())
    ts = _now_ts()
    output_dir = Path(s.backup_output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="nasri-backup-") as tmp:
        tmp_tar = Path(tmp) / "data.tar.gz"
        _build_archive(tmp_tar, _source_paths())
        if not tmp_tar.exists():
            raise BackupError("Yedeklenecek kaynak bulunamadı.")

        if s.backup_encrypt_enabled:
            out = output_dir / f"backup-{ts}-{backup_id}.bin"
            _encrypt_file(tmp_tar, out)
            encrypted = True
        else:
            out = output_dir / f"backup-{ts}-{backup_id}.tar.gz"
            shutil.copy2(tmp_tar, out)
            encrypted = False

    remote_status = _remote_sync(out)
    _prune_backups(output_dir, s.backup_retention_count)
    size = out.stat().st_size if out.exists() else 0

    payload = {
        "backup_id": backup_id,
        "created_at": ts,
        "output_path": str(out),
        "encrypted": encrypted,
        "size_bytes": int(size),
        "remote_status": remote_status,
        "trigger": trigger,
    }
    await _store_history(payload)
    return payload


async def backup_history(limit: int = 20) -> list[dict]:
    r = get_redis()
    raw = await r.lrange(_HISTORY_KEY, 0, max(0, limit - 1))
    out: list[dict] = []
    for item in raw:
        try:
            out.append(json.loads(item))
        except json.JSONDecodeError:
            continue
    return out
