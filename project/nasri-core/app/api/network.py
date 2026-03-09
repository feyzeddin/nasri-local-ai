from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import AuthSession, require_roles
from app.core.settings import get_settings
from app.schemas.network import (
    NetworkDevice,
    NetworkDiscoverRequest,
    NetworkDiscoverResponse,
)
from app.services.network import NetworkDiscoveryError, discover_devices

router = APIRouter(prefix="/network", tags=["network"])


@router.post("/discover", response_model=NetworkDiscoverResponse)
def network_discover(
    body: NetworkDiscoverRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> NetworkDiscoverResponse:
    try:
        devices = discover_devices(
            target_cidr=body.target_cidr,
            include_mdns=body.include_mdns,
        )
    except NetworkDiscoveryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    target_cidr = body.target_cidr or get_settings().lan_scan_default_cidr
    return NetworkDiscoverResponse(
        target_cidr=target_cidr,
        device_count=len(devices),
        devices=[
            NetworkDevice(
                ip=d.ip,
                hostname=d.hostname,
                source=d.source,
                ownership_score=d.ownership_score,
                ownership_label=d.ownership_label,
            )
            for d in devices
        ],
    )
