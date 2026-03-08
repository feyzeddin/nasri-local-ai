from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import AuthSession, require_roles
from app.core.settings import get_settings
from app.schemas.matter import (
    MatterActionRequest,
    MatterActionResponse,
    MatterDevice,
    MatterDeviceListResponse,
    MatterPairRequest,
    MatterPairResponse,
    MatterStatusResponse,
)
from app.services.matter import (
    MatterError,
    controller_status,
    list_devices,
    pair_device,
    send_action,
)

router = APIRouter(prefix="/matter", tags=["matter"])


@router.get("/status", response_model=MatterStatusResponse)
async def matter_status(
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> MatterStatusResponse:
    try:
        online, detail = await controller_status()
    except MatterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return MatterStatusResponse(
        enabled=get_settings().matter_enabled,
        controller_online=online,
        detail=detail,
    )


@router.get("/devices", response_model=MatterDeviceListResponse)
async def matter_devices(
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> MatterDeviceListResponse:
    try:
        rows = await list_devices()
    except MatterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    devices = [MatterDevice(**x) for x in rows if x.get("device_id") and x.get("name")]
    return MatterDeviceListResponse(count=len(devices), devices=devices)


@router.post("/pair", response_model=MatterPairResponse)
async def matter_pair(
    body: MatterPairRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> MatterPairResponse:
    try:
        accepted, detail = await pair_device(body.code, body.network_hint)
    except MatterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return MatterPairResponse(accepted=accepted, detail=detail)


@router.post("/action", response_model=MatterActionResponse)
async def matter_action(
    body: MatterActionRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> MatterActionResponse:
    try:
        accepted, detail = await send_action(
            device_id=body.device_id,
            action=body.action,
            value=body.value,
        )
    except MatterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return MatterActionResponse(accepted=accepted, device_id=body.device_id, detail=detail)

