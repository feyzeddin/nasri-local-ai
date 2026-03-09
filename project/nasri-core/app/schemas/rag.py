from __future__ import annotations

from pydantic import BaseModel, Field


class RagIndexRequest(BaseModel):
    text: str = Field(..., min_length=1)
    document_id: str | None = None
    source: str | None = None


class RagIndexResponse(BaseModel):
    document_id: str
    chunk_count: int


class RagHit(BaseModel):
    text: str
    score: float
    source: str | None = None
    chunk_id: str | None = None


class RagQueryResponse(BaseModel):
    query: str
    top_k: int
    hits: list[RagHit]

