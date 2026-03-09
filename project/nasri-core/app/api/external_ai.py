from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import AuthSession, require_roles
from app.schemas.external_ai import (
    ExternalAIChatRequest,
    ExternalAIChatResponse,
    ExternalAIUsage,
)
from app.services.external_ai import (
    ExternalAIError,
    ExternalAIRateLimitError,
    send_chat,
)

router = APIRouter(prefix="/external-ai", tags=["external-ai"])


@router.post("/chat", response_model=ExternalAIChatResponse)
async def external_ai_chat(
    body: ExternalAIChatRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> ExternalAIChatResponse:
    try:
        result = await send_chat(
            provider=body.provider,
            prompt=body.message,
            system_prompt=body.system_prompt,
        )
    except ExternalAIRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ExternalAIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ExternalAIChatResponse(
        provider=result.provider,  # type: ignore[arg-type]
        model=result.model,
        reply=result.reply,
        anonymized=result.anonymized,
        usage=ExternalAIUsage(
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost_usd=result.cost_usd,
        ),
    )
