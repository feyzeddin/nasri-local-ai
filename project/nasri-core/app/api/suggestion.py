from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import AuthSession, require_roles
from app.schemas.suggestion import ProactiveSuggestionResponse, SuggestionItem
from app.services.suggestion import SuggestionError, generate_proactive_suggestions

router = APIRouter(prefix="/suggestions", tags=["suggestions"])


@router.get("/proactive", response_model=ProactiveSuggestionResponse)
def proactive_suggestions(
    profile_id: str = Query(..., min_length=1),
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> ProactiveSuggestionResponse:
    try:
        items = generate_proactive_suggestions(profile_id)
    except SuggestionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProactiveSuggestionResponse(
        profile_id=profile_id,
        count=len(items),
        items=[SuggestionItem(title=i.title, reason=i.reason, priority=i.priority) for i in items],
    )
