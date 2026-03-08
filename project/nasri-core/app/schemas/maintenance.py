from __future__ import annotations

from pydantic import BaseModel


class MaintenanceRunResponse(BaseModel):
    trigger: str
    ran_at: int
    disk: dict[str, dict[str, float]]
    logs: dict[str, int]
    updates: dict[str, str | int]
    ok: bool


class MaintenanceStatusResponse(BaseModel):
    enabled: bool
    interval_hours: int
    last_run_at: int | None
    last_result: str | None
    due: bool
