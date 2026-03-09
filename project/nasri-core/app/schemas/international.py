from __future__ import annotations

from pydantic import BaseModel, Field


class LocaleSetRequest(BaseModel):
    profile_id: str = Field(min_length=1, max_length=100)
    locale: str = Field(min_length=2, max_length=8)


class LocaleResponse(BaseModel):
    profile_id: str
    locale: str


class GDPRExportRequest(BaseModel):
    profile_id: str = Field(min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=255)


class GDPRExportResponse(BaseModel):
    profile_id: str
    locale: str
    data: dict


class GDPRDeleteResponse(BaseModel):
    profile_id: str
    deleted_keys: int
    detail: str

