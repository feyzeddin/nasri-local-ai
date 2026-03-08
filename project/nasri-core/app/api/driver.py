from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import AuthSession, require_roles
from app.schemas.driver import (
    DriverDevice,
    DriverInstallRequest,
    DriverInstallResponse,
    DriverScanResponse,
)
from app.services.driver import DriverManagerError, install_driver, scan_missing_drivers

router = APIRouter(prefix="/driver", tags=["driver"])


@router.get("/scan", response_model=DriverScanResponse)
def driver_scan(
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> DriverScanResponse:
    try:
        os_name, devices = scan_missing_drivers()
    except DriverManagerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DriverScanResponse(
        os_name=os_name,
        device_count=len(devices),
        devices=[
            DriverDevice(device_id=d.device_id, name=d.name, status=d.status) for d in devices
        ],
    )


@router.post("/install", response_model=DriverInstallResponse)
def driver_install(
    body: DriverInstallRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> DriverInstallResponse:
    try:
        installed, detail = install_driver(
            device_id=body.device_id,
            auto_confirm=body.auto_confirm,
        )
    except DriverManagerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DriverInstallResponse(device_id=body.device_id, installed=installed, detail=detail)
