from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import AuthSession, require_roles
from app.schemas.international import (
    GDPRDeleteResponse,
    GDPRExportRequest,
    GDPRExportResponse,
    LocaleResponse,
    LocaleSetRequest,
)
from app.services.international import (
    InternationalError,
    erase_profile_data,
    export_profile_data,
    get_locale,
    set_locale,
)

router = APIRouter(prefix="/international", tags=["international"])


@router.post("/locale", response_model=LocaleResponse)
async def locale_set(
    body: LocaleSetRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> LocaleResponse:
    try:
        out = await set_locale(body.profile_id, body.locale)
    except InternationalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LocaleResponse(**out)


@router.get("/locale/{profile_id}", response_model=LocaleResponse)
async def locale_get(
    profile_id: str,
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> LocaleResponse:
    out = await get_locale(profile_id)
    return LocaleResponse(**out)


@router.post("/gdpr/export", response_model=GDPRExportResponse)
async def gdpr_export(
    body: GDPRExportRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> GDPRExportResponse:
    out = await export_profile_data(body.profile_id, body.email)
    return GDPRExportResponse(**out)


@router.post("/gdpr/erase", response_model=GDPRDeleteResponse)
async def gdpr_erase(
    body: GDPRExportRequest,
    _session: AuthSession = Depends(require_roles("admin")),
) -> GDPRDeleteResponse:
    deleted = await erase_profile_data(body.profile_id, body.email)
    return GDPRDeleteResponse(
        profile_id=body.profile_id,
        deleted_keys=deleted,
        detail="Profil verileri silindi.",
    )

