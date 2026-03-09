from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import AuthSession, require_roles
from app.schemas.dependency_auditor import (
    DependencyScanResponse,
    DependencyStatusResponse,
)
from app.services.dependency_auditor import (
    DependencyAuditorError,
    get_dependency_status,
    run_dependency_scan,
)

router = APIRouter(prefix="/dependency-auditor", tags=["dependency-auditor"])


@router.get("/status", response_model=DependencyStatusResponse)
async def status(
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> DependencyStatusResponse:
    try:
        out = await get_dependency_status()
    except DependencyAuditorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    last_scan = out.get("last_scan")
    return DependencyStatusResponse(
        enabled=True,
        last_scan=DependencyScanResponse(**last_scan) if isinstance(last_scan, dict) else None,
    )


@router.post("/scan", response_model=DependencyScanResponse)
async def scan(
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> DependencyScanResponse:
    try:
        out = await run_dependency_scan()
    except DependencyAuditorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DependencyScanResponse(**out)

