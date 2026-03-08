from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import AuthSession, require_roles
from app.core.settings import get_settings
from app.schemas.files import FileEntry, FileListResponse

router = APIRouter(prefix="/files", tags=["files"])


def _root() -> Path:
    return Path(get_settings().files_root).expanduser().resolve()


def _safe_target(relative_path: str | None) -> Path:
    root = _root()
    target = (root / (relative_path or ".")).resolve()
    if root != target and root not in target.parents:
        raise HTTPException(status_code=400, detail="Geçersiz path.")
    return target


@router.get("/list", response_model=FileListResponse)
def list_files(
    path: str | None = Query(default=None),
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> FileListResponse:
    target = _safe_target(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Path bulunamadı.")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Path bir klasör olmalı.")

    entries: list[FileEntry] = []
    for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        try:
            stat = item.stat()
            size = int(stat.st_size)
        except OSError:
            size = 0
        entries.append(
            FileEntry(
                path=str(item.relative_to(_root())),
                is_dir=item.is_dir(),
                size=size,
            )
        )

    return FileListResponse(root=str(_root()), entries=entries, count=len(entries))


@router.get("/search", response_model=FileListResponse)
def search_files(
    q: str = Query(..., min_length=1),
    path: str | None = Query(default=None),
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> FileListResponse:
    target = _safe_target(path)
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="Arama dizini bulunamadı.")

    q_lower = q.lower()
    max_results = get_settings().files_max_results
    found: list[FileEntry] = []
    for item in target.rglob("*"):
        if len(found) >= max_results:
            break
        name = item.name.lower()
        if q_lower not in name:
            continue
        try:
            stat = item.stat()
            size = int(stat.st_size)
        except OSError:
            size = 0
        found.append(
            FileEntry(
                path=str(item.relative_to(_root())),
                is_dir=item.is_dir(),
                size=size,
            )
        )

    return FileListResponse(root=str(_root()), entries=found, count=len(found))

