from __future__ import annotations

from pydantic import BaseModel, Field


class OnboardingStartRequest(BaseModel):
    session_id: str | None = Field(default=None)


class OnboardingAnswerRequest(BaseModel):
    session_id: str
    answer: str = Field(..., min_length=1, max_length=500)


class OnboardingStateResponse(BaseModel):
    session_id: str
    step: int
    total_steps: int
    completed: bool
    next_question: str | None
    answers: dict[str, str]

