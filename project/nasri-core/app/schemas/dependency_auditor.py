from __future__ import annotations

from pydantic import BaseModel, Field


class DependencyIssue(BaseModel):
    ecosystem: str
    package: str
    current_version: str
    latest_version: str
    severity: str = "unknown"
    detail: str | None = None


class DependencyScanResponse(BaseModel):
    scan_id: str
    ok: bool
    issue_count: int
    issues: list[DependencyIssue]
    duration_ms: int
    started_at: str
    raw_output: str = Field(default="")


class DependencyStatusResponse(BaseModel):
    enabled: bool
    last_scan: DependencyScanResponse | None

