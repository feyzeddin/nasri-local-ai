from __future__ import annotations

from pydantic import BaseModel, Field


class PairingStartRequest(BaseModel):
    channel: str = Field(..., description="telegram | whatsapp")
    external_user_id: str = Field(..., min_length=1, max_length=128)
    chat_id: str | None = Field(default=None, max_length=128)


class PairingStartResponse(BaseModel):
    pair_code: str
    expires_in_seconds: int
    instruction: str


class PairingConfirmRequest(BaseModel):
    pair_code: str = Field(..., min_length=6, max_length=32)
    force_replace_owner: bool = False


class OwnerBindingResponse(BaseModel):
    channel: str
    external_user_id: str
    chat_id: str | None = None
    linked_at: str

