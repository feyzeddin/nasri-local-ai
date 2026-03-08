from __future__ import annotations

from pydantic import BaseModel, Field


class ResearchQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    max_results: int | None = Field(default=None, ge=1, le=10)
    save_report: bool = True


class ResearchItem(BaseModel):
    title: str
    url: str
    source: str
    summary: str


class ResearchQueryResponse(BaseModel):
    query: str
    item_count: int
    items: list[ResearchItem]
    report_path: str | None = None
