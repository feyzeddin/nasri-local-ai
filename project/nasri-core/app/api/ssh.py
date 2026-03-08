from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from app.core.security import AuthSession, require_roles
from app.schemas.ssh import (
    SSHDownloadRequest,
    SSHExecRequest,
    SSHExecResponse,
    SSHProfileCreateRequest,
    SSHProfileResponse,
    SSHTransferResponse,
    SSHUploadRequest,
)
from app.services.ssh import (
    SSHError,
    delete_profile,
    download_file,
    exec_command,
    get_profile,
    save_profile,
    upload_file,
)

router = APIRouter(prefix="/ssh", tags=["ssh"])


@router.post("/profiles", response_model=SSHProfileResponse)
async def ssh_create_profile(
    body: SSHProfileCreateRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> SSHProfileResponse:
    try:
        p = await save_profile(
            profile_name=body.profile_name,
            host=body.host,
            port=body.port,
            username=body.username,
            auth_method=body.auth_method,
            password=body.password,
            private_key=body.private_key,
            private_key_passphrase=body.private_key_passphrase,
        )
    except SSHError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SSHProfileResponse(
        profile_name=p.profile_name,
        host=p.host,
        port=p.port,
        username=p.username,
        auth_method=p.auth_method,  # type: ignore[arg-type]
    )


@router.get("/profiles/{profile_name}", response_model=SSHProfileResponse)
async def ssh_get_profile(
    profile_name: str,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> SSHProfileResponse:
    try:
        p = await get_profile(profile_name)
    except SSHError as exc:
        if "bulunamadı" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SSHProfileResponse(
        profile_name=p.profile_name,
        host=p.host,
        port=p.port,
        username=p.username,
        auth_method=p.auth_method,  # type: ignore[arg-type]
    )


@router.delete("/profiles/{profile_name}", status_code=204)
async def ssh_delete_profile(
    profile_name: str,
    _session: AuthSession = Depends(require_roles("admin")),
) -> Response:
    try:
        await delete_profile(profile_name)
    except SSHError as exc:
        if "bulunamadı" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(status_code=204)


@router.post("/exec", response_model=SSHExecResponse)
async def ssh_exec(
    body: SSHExecRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> SSHExecResponse:
    try:
        code, out, err = await exec_command(
            profile_name=body.profile_name,
            command=body.command,
            timeout_seconds=body.timeout_seconds,
        )
    except SSHError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return SSHExecResponse(
        profile_name=body.profile_name,
        exit_code=code,
        stdout=out,
        stderr=err,
    )


@router.post("/upload", response_model=SSHTransferResponse)
async def ssh_upload(
    body: SSHUploadRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> SSHTransferResponse:
    try:
        await upload_file(
            profile_name=body.profile_name,
            local_path=body.local_path,
            remote_path=body.remote_path,
        )
    except SSHError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return SSHTransferResponse(
        profile_name=body.profile_name,
        source_path=body.local_path,
        destination_path=body.remote_path,
        transferred=True,
    )


@router.post("/download", response_model=SSHTransferResponse)
async def ssh_download(
    body: SSHDownloadRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> SSHTransferResponse:
    try:
        await download_file(
            profile_name=body.profile_name,
            remote_path=body.remote_path,
            local_path=body.local_path,
        )
    except SSHError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return SSHTransferResponse(
        profile_name=body.profile_name,
        source_path=body.remote_path,
        destination_path=body.local_path,
        transferred=True,
    )
