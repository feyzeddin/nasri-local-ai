from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app.core.security import (
    AuthSession,
    create_auth_session,
    delete_auth_session,
    get_current_session,
    validate_user_credentials,
)
from app.schemas.auth import LoginRequest, LoginResponse, MeResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest) -> LoginResponse:
    role = await validate_user_credentials(body.username, body.password)
    if role is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz kullanıcı adı veya parola.",
        )
    token, ttl = await create_auth_session(body.username, role)
    return LoginResponse(access_token=token, expires_in=ttl, role=role)


@router.get("/me", response_model=MeResponse)
async def me(session: AuthSession = Depends(get_current_session)) -> MeResponse:
    return MeResponse(username=session.username, role=session.role)


@router.post("/logout", status_code=204)
async def logout(session: AuthSession = Depends(get_current_session)) -> Response:
    await delete_auth_session(session.token)
    return Response(status_code=204)
