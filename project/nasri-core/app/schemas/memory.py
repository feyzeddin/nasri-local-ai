from __future__ import annotations

from pydantic import BaseModel, Field


class MemoryStoreRequest(BaseModel):
    profile_id: str = Field(..., min_length=1, max_length=100)
    text: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)


class MemoryStoreResponse(BaseModel):
    memory_id: str
    profile_id: str


class MemoryRecallResponseItem(BaseModel):
    memory_id: str
    text: str
    score: float
    tags: list[str]


class MemoryRecallResponse(BaseModel):
    profile_id: str
    query: str
    top_k: int
    items: list[MemoryRecallResponseItem]

