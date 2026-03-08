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


class SessionStartRequest(BaseModel):
    """Oturum başlatma isteği. system_prompt verilmezse settings'teki kullanılır."""

    session_id: str | None = Field(default=None)
    system_prompt: str | None = Field(
        default=None,
        description="Bu oturuma özel sistem mesajı. Boşsa NASRI_SYSTEM_PROMPT env kullanılır.",
    )


class SessionStartResponse(BaseModel):
    session_id: str
    system_prompt: str | None


class HistoryResponse(BaseModel):
    session_id: str
    messages: list[dict[str, str]]
    count: int
