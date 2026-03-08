from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import AuthSession, require_roles
from app.schemas.maintenance import MaintenanceRunResponse, MaintenanceStatusResponse
from app.services.maintenance import (
    MaintenanceError,
    get_maintenance_status,
    run_maintenance,
)

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.get("/status", response_model=MaintenanceStatusResponse)
async def maintenance_status(
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> MaintenanceStatusResponse:
    status = await get_maintenance_status()
    return MaintenanceStatusResponse(**status)


@router.post("/run", response_model=MaintenanceRunResponse)
async def maintenance_run(
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> MaintenanceRunResponse:
    try:
        result = await run_maintenance(trigger="manual")
    except MaintenanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return MaintenanceRunResponse(**result)
