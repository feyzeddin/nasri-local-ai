"""Chat endpoint request/response şemaları."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Kullanıcı mesajı")
    session_id: str | None = Field(
        default=None,
        description="Oturum kimliği. Boş bırakılırsa sunucu yeni bir UUID üretir.",
    )


class ChatResponse(BaseModel):
    """Streaming olmayan yanıt için (test / debug amaçlı)."""

    reply: str
    session_id: str
