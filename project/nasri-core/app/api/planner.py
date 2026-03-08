from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import AuthSession, require_roles
from app.schemas.planner import PlannerRunRequest, PlannerRunResponse, PlannerStep
from app.services.planner import PlannerError, run_planner

router = APIRouter(prefix="/planner", tags=["planner"])


@router.post("/run", response_model=PlannerRunResponse)
def planner_run(
    body: PlannerRunRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> PlannerRunResponse:
    try:
        completed, summary, steps = run_planner(body.goal, profile_id=body.profile_id)
    except PlannerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PlannerRunResponse(
        goal=body.goal,
        completed=completed,
        summary=summary,
        steps=[
            PlannerStep(
                thought=s.thought,
                action=s.action,
                input=s.action_input,
                observation=s.observation,
            )
            for s in steps
        ],
    )

