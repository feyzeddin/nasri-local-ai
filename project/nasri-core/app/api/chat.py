"""POST /chat — Ollama'ya mesaj iletir, yanıtı stream eder.

Konuşma geçmişi Redis'te saklanır; her istekte önceki mesajlar
Ollama bağlamına eklenir (F9.3).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.core.redis import append_messages, load_history
from app.core.settings import get_settings
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.llm import OllamaClient, OllamaError

router = APIRouter(prefix="/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------


def _make_client() -> OllamaClient:
    s = get_settings()
    return OllamaClient(base_url=s.ollama_url, model=s.model_name)


def _ensure_session(session_id: str | None) -> str:
    return session_id or str(uuid.uuid4())


async def _build_messages(session_id: str, new_message: str) -> list[dict[str, str]]:
    """Redis geçmişini okur, yeni kullanıcı mesajını ekler ve döner."""
    history = await load_history(session_id)
    return history + [{"role": "user", "content": new_message}]


# ---------------------------------------------------------------------------
# Streaming endpoint — üretime yönelik
# ---------------------------------------------------------------------------


@router.post("/stream")
async def chat_stream(body: ChatRequest) -> StreamingResponse:
    """Ollama yanıtını Server-Sent Events (text/event-stream) olarak akıtır.

    Her chunk `data: <token>\\n\\n` formatında gönderilir.
    Akış bitince `data: [DONE]\\n\\n` gönderilir.
    Oturum geçmişi Redis'te güncellenir.
    """
    session_id = _ensure_session(body.session_id)
    messages = await _build_messages(session_id, body.message)
    client = _make_client()

    async def event_generator() -> AsyncIterator[str]:
        collected: list[str] = []
        try:
            async for chunk in client.chat_stream(messages):
                if chunk:
                    collected.append(chunk)
                    yield f"data: {chunk}\n\n"
        except OllamaError as exc:
            yield f"data: [ERROR] {exc}\n\n"
            return
        finally:
            yield "data: [DONE]\n\n"

        # Geçmişi kaydet: kullanıcı mesajı + asistan yanıtı
        reply = "".join(collected)
        await append_messages(
            session_id,
            [
                {"role": "user", "content": body.message},
                {"role": "assistant", "content": reply},
            ],
        )

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

    Konuşma geçmişini Redis'ten okur ve günceller.
    Geliştirme ve test için kullanışlıdır.
    Üretim ortamında /chat/stream tercih edilmeli.
    """
    session_id = _ensure_session(body.session_id)
    messages = await _build_messages(session_id, body.message)
    client = _make_client()

    try:
        reply = await client.chat(messages)
    except OllamaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    await append_messages(
        session_id,
        [
            {"role": "user", "content": body.message},
            {"role": "assistant", "content": reply},
        ],
    )

    return ChatResponse(reply=reply, session_id=session_id)
