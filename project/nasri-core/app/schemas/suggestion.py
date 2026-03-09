from __future__ import annotations

from pydantic import BaseModel, Field


class SuggestionItem(BaseModel):
    title: str
    reason: str
    priority: int = Field(ge=1, le=5)


class ProactiveSuggestionResponse(BaseModel):
    profile_id: str
    count: int
    items: list[SuggestionItem]
