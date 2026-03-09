from __future__ import annotations

from pydantic import BaseModel, Field


class PlannerRunRequest(BaseModel):
    goal: str = Field(..., min_length=1)
    profile_id: str | None = None


class PlannerStep(BaseModel):
    thought: str
    action: str
    input: str
    observation: str


class PlannerRunResponse(BaseModel):
    goal: str
    completed: bool
    summary: str
    steps: list[PlannerStep]

