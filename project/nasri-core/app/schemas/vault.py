from __future__ import annotations

from pydantic import BaseModel, Field


class VaultSetRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    value: str = Field(..., min_length=1, max_length=10000)


class VaultGetResponse(BaseModel):
    name: str
    value: str
    key_id: str


class VaultSetResponse(BaseModel):
    name: str
    key_id: str

