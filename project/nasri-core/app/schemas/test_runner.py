from __future__ import annotations

from pydantic import BaseModel, Field


class TestRunnerRunRequest(BaseModel):
    target: str | None = Field(default=None, max_length=256)
    keyword: str | None = Field(default=None, max_length=128)


class TestRunnerResult(BaseModel):
    run_id: str
    command: list[str]
    target: str
    keyword: str | None
    return_code: int
    ok: bool
    duration_ms: int
    output: str
    started_at: str


class TestRunnerStatusResponse(BaseModel):
    enabled: bool
    last_run: TestRunnerResult | None


class TestRunnerHistoryResponse(BaseModel):
    count: int
    items: list[TestRunnerResult]

