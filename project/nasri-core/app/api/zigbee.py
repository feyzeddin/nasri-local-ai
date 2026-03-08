from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import AuthSession, require_roles
from app.core.settings import get_settings
from app.schemas.zigbee import (
    ZigbeeActionRequest,
    ZigbeeActionResponse,
    ZigbeeDevice,
    ZigbeeDeviceListResponse,
    ZigbeePermitJoinRequest,
    ZigbeePermitJoinResponse,
    ZigbeeStatusResponse,
)
from app.services.zigbee import (
    ZigbeeError,
    bridge_status,
    list_devices,
    permit_join,
    send_device_action,
)

router = APIRouter(prefix="/zigbee", tags=["zigbee"])


@router.get("/status", response_model=ZigbeeStatusResponse)
async def zigbee_status(
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> ZigbeeStatusResponse:
    try:
        online, detail = await bridge_status()
    except ZigbeeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ZigbeeStatusResponse(
        enabled=get_settings().zigbee_enabled,
        bridge_online=online,
        detail=detail,
    )


@router.get("/devices", response_model=ZigbeeDeviceListResponse)
async def zigbee_devices(
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> ZigbeeDeviceListResponse:
    try:
        rows = await list_devices()
    except ZigbeeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    devices = [ZigbeeDevice(**x) for x in rows if x.get("friendly_name")]
    return ZigbeeDeviceListResponse(count=len(devices), devices=devices)


@router.post("/permit-join", response_model=ZigbeePermitJoinResponse)
async def zigbee_permit_join(
    body: ZigbeePermitJoinRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> ZigbeePermitJoinResponse:
    try:
        accepted, detail = await permit_join(body.seconds)
    except ZigbeeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ZigbeePermitJoinResponse(accepted=accepted, seconds=body.seconds, detail=detail)


@router.post("/action", response_model=ZigbeeActionResponse)
async def zigbee_action(
    body: ZigbeeActionRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> ZigbeeActionResponse:
    try:
        accepted, detail = await send_device_action(
            friendly_name=body.friendly_name,
            action=body.action,
            value=body.value,
        )
    except ZigbeeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ZigbeeActionResponse(
        accepted=accepted,
        friendly_name=body.friendly_name,
        detail=detail,
    )
