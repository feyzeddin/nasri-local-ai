from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import AuthSession, require_roles
from app.schemas.beta_program import (
    BetaCandidate,
    BetaCandidateListResponse,
    BetaCandidateRequest,
    BetaFeedbackItem,
    BetaFeedbackListResponse,
    BetaFeedbackRequest,
)
from app.services.beta_program import (
    BetaProgramError,
    create_candidate,
    create_feedback,
    list_candidates,
    list_feedback,
)

router = APIRouter(prefix="/beta-program", tags=["beta-program"])


@router.post("/candidates", response_model=BetaCandidate)
async def add_candidate(
    body: BetaCandidateRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> BetaCandidate:
    try:
        out = await create_candidate(
            name=body.name,
            email=body.email,
            nda_accepted=body.nda_accepted,
            note=body.note,
        )
    except BetaProgramError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BetaCandidate(**out)


@router.get("/candidates", response_model=BetaCandidateListResponse)
async def get_candidates(
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> BetaCandidateListResponse:
    try:
        items = await list_candidates()
    except BetaProgramError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BetaCandidateListResponse(count=len(items), items=[BetaCandidate(**x) for x in items])


@router.post("/feedback", response_model=BetaFeedbackItem)
async def add_feedback(
    body: BetaFeedbackRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> BetaFeedbackItem:
    try:
        out = await create_feedback(
            candidate_id=body.candidate_id,
            score=body.score,
            text=body.text,
        )
    except BetaProgramError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BetaFeedbackItem(**out)


@router.get("/feedback", response_model=BetaFeedbackListResponse)
async def get_feedback(
    limit: int = Query(default=50, ge=1, le=200),
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> BetaFeedbackListResponse:
    try:
        items = await list_feedback(limit=limit)
    except BetaProgramError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BetaFeedbackListResponse(count=len(items), items=[BetaFeedbackItem(**x) for x in items])

