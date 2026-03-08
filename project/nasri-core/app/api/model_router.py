from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import AuthSession, require_roles
from app.schemas.model_router import (
    ModelRouterAttempt,
    ModelRouterChatRequest,
    ModelRouterChatResponse,
)
from app.services.model_router import ModelRouterError, route_chat

router = APIRouter(prefix="/model-router", tags=["model-router"])


@router.post("/chat", response_model=ModelRouterChatResponse)
async def model_router_chat(
    body: ModelRouterChatRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> ModelRouterChatResponse:
    try:
        result = await route_chat(
            prompt=body.message,
            system_prompt=body.system_prompt,
            preferred_tier=body.preferred_tier,
        )
    except ModelRouterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ModelRouterChatResponse(
        reply=result.reply,
        used_tier=result.used_tier,
        attempts=[
            ModelRouterAttempt(tier=a.tier, status=a.status, detail=a.detail)
            for a in result.attempts
        ],
    )
