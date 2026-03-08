from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import AuthSession, require_roles
from app.schemas.self_heal import SelfHealAction, SelfHealRunResponse, SelfHealStatusResponse
from app.services.self_heal import SelfHealError, run_self_heal, self_heal_status

router = APIRouter(prefix="/self-heal", tags=["self-heal"])


@router.get("/status", response_model=SelfHealStatusResponse)
def status(
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> SelfHealStatusResponse:
    return SelfHealStatusResponse(**self_heal_status())


@router.post("/run", response_model=SelfHealRunResponse)
async def run(
    force: bool = Query(default=False),
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> SelfHealRunResponse:
    try:
        issues, actions, healed = await run_self_heal(force=force)
    except SelfHealError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SelfHealRunResponse(
        issue_count=len(issues),
        issues=issues,
        actions=[SelfHealAction(action=a.action, executed=a.executed, detail=a.detail) for a in actions],
        healed=healed,
    )
