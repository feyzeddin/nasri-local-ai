from __future__ import annotations

from pydantic import BaseModel


class SelfHealStatusResponse(BaseModel):
    enabled: bool
    auto_fix: bool
    anomaly_limit: int


class SelfHealAction(BaseModel):
    action: str
    executed: bool
    detail: str


class SelfHealRunResponse(BaseModel):
    issue_count: int
    issues: list[str]
    actions: list[SelfHealAction]
    healed: bool
