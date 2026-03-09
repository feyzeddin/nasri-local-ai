from __future__ import annotations

from pydantic import BaseModel, Field


class AgentNetworkRunRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=4000)
    profile_id: str | None = Field(default=None, max_length=100)
    agents: list[str] = Field(default_factory=lambda: ["planner", "memory", "risk"])
    parallel: bool = True


class AgentNetworkAgentResult(BaseModel):
    agent: str
    ok: bool
    detail: str


class AgentNetworkRunResponse(BaseModel):
    run_id: str
    goal: str
    profile_id: str | None
    parallel: bool
    completed: bool
    summary: str
    results: list[AgentNetworkAgentResult]
    created_at: str


class AgentNetworkRunListResponse(BaseModel):
    count: int
    items: list[AgentNetworkRunResponse]

