from __future__ import annotations

from pydantic import BaseModel


class FileEntry(BaseModel):
    path: str
    is_dir: bool
    size: int


class FileListResponse(BaseModel):
    root: str
    entries: list[FileEntry]
    count: int

