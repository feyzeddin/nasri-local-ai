from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from app.core.security import AuthSession, require_roles
from app.schemas.identity import (
    IdentityEnrollRequest,
    IdentityVerifyRequest,
    IdentityVerifyResponse,
)
from app.services.identity import IdentityError, enroll_identity, verify_identity

router = APIRouter(prefix="/identity", tags=["identity"])


@router.post("/enroll", status_code=204)
async def enroll(
    body: IdentityEnrollRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> Response:
    await enroll_identity(body.profile_id, body.device, body.biometric_sample)
    return Response(status_code=204)


@router.post("/verify", response_model=IdentityVerifyResponse)
async def verify(
    body: IdentityVerifyRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> IdentityVerifyResponse:
    try:
        return await verify_identity(body.profile_id, body.device, body.biometric_sample)
    except IdentityError as exc:
        if "bulunamadı" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=502, detail=str(exc)) from exc

