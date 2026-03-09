from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import AuthSession, require_roles
from app.schemas.agent_network import (
    AgentNetworkAgentResult,
    AgentNetworkRunListResponse,
    AgentNetworkRunRequest,
    AgentNetworkRunResponse,
)
from app.services.agent_network import (
    AgentNetworkError,
    get_run,
    list_runs,
    run_agent_network,
)

router = APIRouter(prefix="/agent-network", tags=["agent-network"])


@router.post("/run", response_model=AgentNetworkRunResponse)
async def run(
    body: AgentNetworkRunRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> AgentNetworkRunResponse:
    try:
        out = await run_agent_network(
            goal=body.goal,
            profile_id=body.profile_id,
            agents=body.agents,
            parallel=body.parallel,
        )
    except AgentNetworkError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AgentNetworkRunResponse(
        run_id=out["run_id"],
        goal=out["goal"],
        profile_id=out["profile_id"],
        parallel=out["parallel"],
        completed=out["completed"],
        summary=out["summary"],
        results=[AgentNetworkAgentResult(**x) for x in out["results"]],
        created_at=out["created_at"],
    )


@router.get("/runs/{run_id}", response_model=AgentNetworkRunResponse)
async def run_item(
    run_id: str,
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> AgentNetworkRunResponse:
    try:
        out = await get_run(run_id)
    except AgentNetworkError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if out is None:
        raise HTTPException(status_code=404, detail="Run bulunamadı.")
    return AgentNetworkRunResponse(
        run_id=out["run_id"],
        goal=out["goal"],
        profile_id=out.get("profile_id"),
        parallel=out["parallel"],
        completed=out["completed"],
        summary=out["summary"],
        results=[AgentNetworkAgentResult(**x) for x in out["results"]],
        created_at=out["created_at"],
    )


@router.get("/runs", response_model=AgentNetworkRunListResponse)
async def runs(
    limit: int = Query(default=50, ge=1, le=200),
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> AgentNetworkRunListResponse:
    try:
        rows = await list_runs(limit=limit)
    except AgentNetworkError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    items = [
        AgentNetworkRunResponse(
            run_id=x["run_id"],
            goal=x["goal"],
            profile_id=x.get("profile_id"),
            parallel=x["parallel"],
            completed=x["completed"],
            summary=x["summary"],
            results=[AgentNetworkAgentResult(**r) for r in x["results"]],
            created_at=x["created_at"],
        )
        for x in rows
    ]
    return AgentNetworkRunListResponse(count=len(items), items=items)

