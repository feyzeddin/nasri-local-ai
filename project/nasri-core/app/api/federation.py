from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from app.core.security import AuthSession, require_roles
from app.core.settings import get_settings
from app.schemas.federation import (
    FederationDispatchRequest,
    FederationDispatchResponse,
    FederationInboxRequest,
    FederationInboxResponse,
    FederationPeer,
    FederationPeerListResponse,
    FederationPeerRegisterRequest,
)
from app.services.federation import (
    FederationError,
    dispatch_to_peer,
    list_peers,
    register_peer,
    remove_peer,
    verify_shared_token,
)

router = APIRouter(prefix="/federation", tags=["federation"])


@router.post("/peers", response_model=FederationPeer)
async def create_peer(
    body: FederationPeerRegisterRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> FederationPeer:
    try:
        item = await register_peer(
            peer_id=body.peer_id,
            base_url=body.base_url,
            token=body.token,
        )
    except FederationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FederationPeer(peer_id=item.peer_id, base_url=item.base_url, has_token=item.has_token)


@router.get("/peers", response_model=FederationPeerListResponse)
async def peers(
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> FederationPeerListResponse:
    try:
        items = await list_peers()
    except FederationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FederationPeerListResponse(
        count=len(items),
        peers=[FederationPeer(peer_id=x.peer_id, base_url=x.base_url, has_token=x.has_token) for x in items],
    )


@router.delete("/peers/{peer_id}")
async def delete_peer(
    peer_id: str,
    _session: AuthSession = Depends(require_roles("admin")),
) -> dict[str, bool]:
    try:
        deleted = await remove_peer(peer_id)
    except FederationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"deleted": deleted}


@router.post("/dispatch", response_model=FederationDispatchResponse)
async def dispatch(
    body: FederationDispatchRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> FederationDispatchResponse:
    try:
        status_code, detail = await dispatch_to_peer(
            peer_id=body.peer_id,
            path=body.path,
            payload=body.payload,
        )
    except FederationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FederationDispatchResponse(peer_id=body.peer_id, status_code=status_code, detail=detail)


@router.post("/inbox", response_model=FederationInboxResponse)
async def inbox(
    body: FederationInboxRequest,
    x_federation_token: str | None = Header(default=None),
) -> FederationInboxResponse:
    try:
        verify_shared_token(x_federation_token)
    except FederationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return FederationInboxResponse(
        accepted=True,
        node_id=get_settings().federation_node_id,
        detail=f"Payload alındı: {body.source_node_id}",
    )

