from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from app.core.security import AuthSession, require_roles
from app.schemas.vault import VaultGetResponse, VaultSetRequest, VaultSetResponse
from app.services.vault import VaultError, delete_secret, get_secret, set_secret

router = APIRouter(prefix="/vault", tags=["vault"])


@router.post("/secrets", response_model=VaultSetResponse)
async def vault_set(
    body: VaultSetRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> VaultSetResponse:
    try:
        key_id = await set_secret(body.name, body.value)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return VaultSetResponse(name=body.name, key_id=key_id)


@router.get("/secrets/{name}", response_model=VaultGetResponse)
async def vault_get(
    name: str,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> VaultGetResponse:
    try:
        value, key_id = await get_secret(name)
    except VaultError as exc:
        if "bulunamadı" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return VaultGetResponse(name=name, value=value, key_id=key_id)


@router.delete("/secrets/{name}", status_code=204)
async def vault_delete(
    name: str,
    _session: AuthSession = Depends(require_roles("admin")),
) -> Response:
    await delete_secret(name)
    return Response(status_code=204)

