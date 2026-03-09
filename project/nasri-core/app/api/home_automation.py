from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import AuthSession, require_roles
from app.schemas.home_automation import (
    HomeAutomationCommandRequest,
    HomeAutomationCommandResponse,
)
from app.services.home_automation import HomeAutomationError, run_command

router = APIRouter(prefix="/home-automation", tags=["home-automation"])


@router.post("/command", response_model=HomeAutomationCommandResponse)
async def home_automation_command(
    body: HomeAutomationCommandRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> HomeAutomationCommandResponse:
    try:
        mode_used, action, target = await run_command(
            command_text=body.command_text,
            mode=body.mode,
        )
    except HomeAutomationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return HomeAutomationCommandResponse(
        mode_used=mode_used,  # type: ignore[arg-type]
        action=action,
        target=target,
        detail=f"{target}:{action} komutu {mode_used} ile işlendi.",
    )
