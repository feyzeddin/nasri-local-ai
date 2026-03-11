"""
notifications.py — Dosya tabanlı bildirim sistemi.

Servis ve diğer bileşenler push() ile bildirim yazar.
`nasri watch` TUI'si bu dosyayı okur.
Atomic write (tmp → rename) ile yarım-okuma riskini önler.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import secrets
import tempfile
from pathlib import Path

from .config import data_dir

_FILE_NAME = "notifications.json"
_MAX_ITEMS = 100


def _notifications_file() -> Path:
    return data_dir() / _FILE_NAME


def _load() -> list[dict]:
    path = _notifications_file()
    if not path.exists():
        return []
    for _ in range(3):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save(items: list[dict]) -> None:
    path = _notifications_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(items, ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def push(title: str, message: str, kind: str = "info") -> None:
    """kind: info | update | action | error | warning"""
    items = _load()
    items.insert(0, {
        "id": secrets.token_hex(6),
        "kind": kind,
        "title": title,
        "message": message,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "read": False,
    })
    _save(items[:_MAX_ITEMS])


def list_all(unread_only: bool = False) -> list[dict]:
    items = _load()
    if unread_only:
        return [i for i in items if not i.get("read")]
    return items


def mark_all_read() -> None:
    items = _load()
    for item in items:
        item["read"] = True
    _save(items)


def clear() -> None:
    _save([])
