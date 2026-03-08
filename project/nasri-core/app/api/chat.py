"""POST /chat — Ollama'ya mesaj iletir, yanıtı stream eder."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.settings import get_settings
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.llm import OllamaClient, OllamaError

router = APIRouter(prefix="/chat", tags=["chat"])


def _make_client() -> OllamaClient:
    s = get_settings()
    return OllamaClient(base_url=s.ollama_url, model=s.model_name)


def _ensure_session(session_id: str | None) -> str:
    return session_id or str(uuid.uuid4())


def _build_messages(message: str) -> list[dict[str, str]]:
    """Şimdilik tek mesajlı bağlam. F9.3'te Redis geçmişi burada birleşecek."""
    return [{"role": "user", "content": message}]


# ---------------------------------------------------------------------------
# Streaming endpoint — üretime yönelik
# ---------------------------------------------------------------------------


@router.post("/stream")
async def chat_stream(body: ChatRequest) -> StreamingResponse:
    """Ollama yanıtını Server-Sent Events (text/event-stream) olarak akıtır.

    Her chunk `data: <token>\\n\\n` formatında gönderilir.
    Akış bitince `data: [DONE]\\n\\n` gönderilir.
    """
    session_id = _ensure_session(body.session_id)
    messages = _build_messages(body.message)
    client = _make_client()

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for chunk in client.chat_stream(messages):
                if chunk:
                    yield f"data: {chunk}\n\n"
        except OllamaError as exc:
            yield f"data: [ERROR] {exc}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    headers = {"X-Session-Id": session_id}
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Non-streaming endpoint — test / debug amaçlı
# ---------------------------------------------------------------------------


@router.post("", response_model=ChatResponse)
async def chat(body: ChatRequest) -> ChatResponse:
    """Ollama'dan tam yanıtı bekler, JSON olarak döner.

    Geliştirme ve test için kullanışlıdır.
    Üretim ortamında /chat/stream tercih edilmeli.
    """
    session_id = _ensure_session(body.session_id)
    messages = _build_messages(body.message)
    client = _make_client()

    try:
        reply = await client.chat(messages)
    except OllamaError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ChatResponse(reply=reply, session_id=session_id)
