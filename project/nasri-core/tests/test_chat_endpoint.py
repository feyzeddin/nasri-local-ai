"""POST /chat ve POST /chat/stream endpoint testleri.

OllamaClient monkeypatch ile sahte yanıt döndürür;
gerçek Ollama sunucusu gerekmez.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

FAKE_REPLY = "Selamunaleyküm!"
FAKE_CHUNKS = ["Sela", "mun", "aleyküm!"]


async def _fake_chat_stream(_messages: list) -> AsyncIterator[str]:
    for chunk in FAKE_CHUNKS:
        yield chunk


# ---------------------------------------------------------------------------
# POST /chat — non-streaming
# ---------------------------------------------------------------------------


def test_chat_returns_reply():
    with patch(
        "app.api.chat.OllamaClient.chat",
        new_callable=AsyncMock,
        return_value=FAKE_REPLY,
    ):
        response = client.post("/chat", json={"message": "Merhaba"})

    assert response.status_code == 200
    data = response.json()
    assert data["reply"] == FAKE_REPLY
    assert "session_id" in data
    assert len(data["session_id"]) > 0


def test_chat_uses_provided_session_id():
    with patch(
        "app.api.chat.OllamaClient.chat",
        new_callable=AsyncMock,
        return_value=FAKE_REPLY,
    ):
        response = client.post(
            "/chat", json={"message": "Merhaba", "session_id": "test-session-123"}
        )

    assert response.status_code == 200
    assert response.json()["session_id"] == "test-session-123"


def test_chat_generates_session_id_when_missing():
    with patch(
        "app.api.chat.OllamaClient.chat",
        new_callable=AsyncMock,
        return_value=FAKE_REPLY,
    ):
        r1 = client.post("/chat", json={"message": "a"})
        r2 = client.post("/chat", json={"message": "b"})

    # Her istekte farklı UUID üretilmeli
    assert r1.json()["session_id"] != r2.json()["session_id"]


def test_chat_rejects_empty_message():
    response = client.post("/chat", json={"message": ""})
    assert response.status_code == 422


def test_chat_returns_502_on_ollama_error():
    from app.services.llm import OllamaError

    with patch(
        "app.api.chat.OllamaClient.chat",
        new_callable=AsyncMock,
        side_effect=OllamaError("Ollama çalışmıyor"),
    ):
        response = client.post("/chat", json={"message": "Merhaba"})

    assert response.status_code == 502
    assert "Ollama" in response.json()["detail"]


# ---------------------------------------------------------------------------
# POST /chat/stream — SSE streaming
# ---------------------------------------------------------------------------


def test_chat_stream_returns_event_stream():
    with patch("app.api.chat.OllamaClient.chat_stream", side_effect=_fake_chat_stream):
        with client.stream("POST", "/chat/stream", json={"message": "Merhaba"}) as r:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers["content-type"]


def test_chat_stream_yields_chunks_and_done():
    with patch("app.api.chat.OllamaClient.chat_stream", side_effect=_fake_chat_stream):
        with client.stream("POST", "/chat/stream", json={"message": "Merhaba"}) as r:
            text = r.read().decode()

    lines = [line for line in text.splitlines() if line.startswith("data: ")]
    data_values = [line[len("data: ") :] for line in lines]

    assert data_values[:3] == FAKE_CHUNKS
    assert data_values[-1] == "[DONE]"


def test_chat_stream_includes_session_id_header():
    with patch("app.api.chat.OllamaClient.chat_stream", side_effect=_fake_chat_stream):
        with client.stream(
            "POST",
            "/chat/stream",
            json={"message": "Merhaba", "session_id": "ses-abc"},
        ) as r:
            assert r.headers.get("x-session-id") == "ses-abc"


def test_chat_stream_rejects_empty_message():
    response = client.post("/chat/stream", json={"message": ""})
    assert response.status_code == 422
