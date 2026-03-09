"""Chat API — Ollama'ya mesaj iletir, oturum yönetir.

Endpoints:
    POST   /chat/session            — yeni oturum başlatır, sistem mesajı atar (F10.3)
    POST   /chat/stream             — SSE akış yanıtı (F9.2)
    POST   /chat                    — tam JSON yanıtı (F9.2)
    GET    /chat/{session_id}/history — konuşma geçmişi (F10.2)
    DELETE /chat/{session_id}       — oturumu siler (F10.1)

Konuşma geçmişi Redis'te saklanır; her istekte önceki mesajlar
Ollama bağlamına eklenir (F9.3).
Sistem mesajı: NASRI_SYSTEM_PROMPT env veya oturuma özel Redis anahtarı (F10.3).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse

from app.core.redis import append_messages, clear_history, load_history
from app.core.settings import get_settings
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    HistoryResponse,
    SessionStartRequest,
    SessionStartResponse,
)
from app.services.llm import OllamaClient, OllamaError
from app.services.model_router import ModelRouterError, route_chat

router = APIRouter(prefix="/chat", tags=["chat"])

_SYS_PREFIX = "sys"


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------


def _make_client() -> OllamaClient:
    s = get_settings()
    return OllamaClient(base_url=s.ollama_url, model=s.model_name)


def _ensure_session(session_id: str | None) -> str:
    return session_id or str(uuid.uuid4())


def _sys_key(session_id: str) -> str:
    """Oturuma özel sistem mesajının Redis anahtarı."""
    return f"{_SYS_PREFIX}:{session_id}"


async def _get_system_prompt(session_id: str) -> str | None:
    """Oturuma özel sistem mesajını Redis'ten okur; yoksa global ayarı döner."""
    sys_msgs = await load_history(_sys_key(session_id))
    if sys_msgs:
        return sys_msgs[0].get("content")
    return get_settings().system_prompt


async def _build_messages(
    session_id: str,
    new_message: str,
) -> list[dict[str, str]]:
    """Sistem mesajı + Redis geçmişi + yeni kullanıcı mesajını birleştirir."""
    history = await load_history(session_id)
    system_prompt = await _get_system_prompt(session_id)

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(history)
    messages.append({"role": "user", "content": new_message})
    return messages


def _messages_to_prompt(messages: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for msg in messages[-10:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            lines.append(f"Sistem: {content}")
        elif role == "assistant":
            lines.append(f"Nasri: {content}")
        else:
            lines.append(f"Kullanıcı: {content}")
    lines.append("Nasri:")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# F10.3 — Oturum başlatma
# ---------------------------------------------------------------------------


@router.post("/session", response_model=SessionStartResponse, status_code=201)
async def start_session(body: SessionStartRequest) -> SessionStartResponse:
    """Yeni bir oturum başlatır ve isteğe bağlı sistem mesajı atar.

    - ``session_id`` verilmezse sunucu yeni UUID üretir.
    - ``system_prompt`` verilirse bu oturuma özel Redis'e kaydedilir.
    - Verilmezse global ``NASRI_SYSTEM_PROMPT`` env değeri kullanılır.
    """
    session_id = _ensure_session(body.session_id)
    effective_prompt: str | None = body.system_prompt

    if effective_prompt:
        # Oturuma özel sistem mesajını Redis'e kaydet
        await append_messages(
            _sys_key(session_id),
            [{"role": "system", "content": effective_prompt}],
        )
    else:
        effective_prompt = get_settings().system_prompt

    return SessionStartResponse(session_id=session_id, system_prompt=effective_prompt)


# ---------------------------------------------------------------------------
# F9.2 — Streaming endpoint
# ---------------------------------------------------------------------------


@router.post("/stream")
async def chat_stream(body: ChatRequest) -> StreamingResponse:
    """Ollama yanıtını Server-Sent Events (text/event-stream) olarak akıtır.

    Her chunk ``data: <token>\\n\\n`` formatında gönderilir.
    Akış bitince ``data: [DONE]\\n\\n`` gönderilir.
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
# F9.2 — Non-streaming endpoint
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
    prompt = _messages_to_prompt(messages)
    try:
        routed = await route_chat(
            prompt=prompt,
            system_prompt=await _get_system_prompt(session_id),
        )
        reply = routed.reply
    except ModelRouterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    await append_messages(
        session_id,
        [
            {"role": "user", "content": body.message},
            {"role": "assistant", "content": reply},
        ],
    )

    return ChatResponse(reply=reply, session_id=session_id)


# ---------------------------------------------------------------------------
# F10.2 — Geçmiş okuma
# ---------------------------------------------------------------------------


@router.get("/{session_id}/history", response_model=HistoryResponse)
async def get_history(session_id: str) -> HistoryResponse:
    """Oturuma ait konuşma geçmişini döner.

    Oturum yoksa boş liste döner (404 atmaz).
    """
    messages = await load_history(session_id)
    return HistoryResponse(
        session_id=session_id,
        messages=messages,
        count=len(messages),
    )


# ---------------------------------------------------------------------------
# F10.1 — Oturum silme
# ---------------------------------------------------------------------------


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str) -> Response:
    """Oturuma ait tüm geçmişi ve sistem mesajını siler.

    Oturum mevcut değilse yine 204 döner (idempotent).
    """
    await clear_history(session_id)
    await clear_history(_sys_key(session_id))
    return Response(status_code=204)
