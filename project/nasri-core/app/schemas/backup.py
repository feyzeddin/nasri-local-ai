from __future__ import annotations

from pydantic import BaseModel


class BackupRunResponse(BaseModel):
    backup_id: str
    created_at: int
    output_path: str
    encrypted: bool
    size_bytes: int
    remote_status: str


class BackupHistoryItem(BaseModel):
    backup_id: str
    created_at: int
    output_path: str
    encrypted: bool
    size_bytes: int
    remote_status: str


class BackupHistoryResponse(BaseModel):
    count: int
    items: list[BackupHistoryItem]
