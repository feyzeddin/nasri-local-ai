from __future__ import annotations

from pydantic import BaseModel, Field


class BetaCandidateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=5, max_length=255)
    nda_accepted: bool = False
    note: str | None = Field(default=None, max_length=500)


class BetaCandidate(BaseModel):
    candidate_id: str
    name: str
    email: str
    nda_accepted: bool
    status: str
    note: str | None = None
    created_at: str


class BetaCandidateListResponse(BaseModel):
    count: int
    items: list[BetaCandidate]


class BetaFeedbackRequest(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=64)
    score: int = Field(ge=1, le=5)
    text: str = Field(min_length=1, max_length=2000)


class BetaFeedbackItem(BaseModel):
    feedback_id: str
    candidate_id: str
    score: int
    text: str
    created_at: str


class BetaFeedbackListResponse(BaseModel):
    count: int
    items: list[BetaFeedbackItem]
