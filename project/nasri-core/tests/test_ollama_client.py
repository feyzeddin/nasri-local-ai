"""OllamaClient unit testleri.

Gercek Ollama sunucusuna ihtiyac duymaz; httpx mock kullanilir.
"""

from __future__ import annotations

import json

import pytest
import httpx

from app.services.llm import OllamaClient, OllamaError


# ---------------------------------------------------------------------------
# Yardimci sabitler
# ---------------------------------------------------------------------------

BASE_URL = "http://localhost:11434"
MODEL = "llama3"
MESSAGES = [{"role": "user", "content": "Merhaba"}]

NON_STREAM_RESPONSE = {
    "model": MODEL,
    "message": {"role": "assistant", "content": "Selamunaleyküm!"},
    "done": True,
}

STREAM_LINES = [
    {"message": {"role": "assistant", "content": "Sela"}, "done": False},
    {"message": {"role": "assistant", "content": "mun"}, "done": False},
    {"message": {"role": "assistant", "content": "aleyküm"}, "done": False},
    {"done": True},
]


def _stream_body(lines: list[dict]) -> bytes:
    return b"\n".join(json.dumps(line).encode() for line in lines)


# ---------------------------------------------------------------------------
# Non-streaming testler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_returns_content(respx_mock):
    respx_mock.post(f"{BASE_URL}/api/chat").mock(
        return_value=httpx.Response(200, json=NON_STREAM_RESPONSE)
    )
    client = OllamaClient(base_url=BASE_URL, model=MODEL)
    result = await client.chat(MESSAGES)
    assert result == "Selamunaleyküm!"


@pytest.mark.asyncio
async def test_chat_raises_on_http_error(respx_mock):
    respx_mock.post(f"{BASE_URL}/api/chat").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )
    client = OllamaClient(base_url=BASE_URL, model=MODEL)
    with pytest.raises(OllamaError, match="HTTP hatasi"):
        await client.chat(MESSAGES)


@pytest.mark.asyncio
async def test_chat_raises_on_connection_error(respx_mock):
    respx_mock.post(f"{BASE_URL}/api/chat").mock(
        side_effect=httpx.ConnectError("baglanti reddedildi")
    )
    client = OllamaClient(base_url=BASE_URL, model=MODEL)
    with pytest.raises(OllamaError, match="baglanti hatasi"):
        await client.chat(MESSAGES)


@pytest.mark.asyncio
async def test_chat_raises_on_malformed_response(respx_mock):
    respx_mock.post(f"{BASE_URL}/api/chat").mock(
        return_value=httpx.Response(200, json={"unexpected": "format"})
    )
    client = OllamaClient(base_url=BASE_URL, model=MODEL)
    with pytest.raises(OllamaError, match="yanit formati"):
        await client.chat(MESSAGES)


# ---------------------------------------------------------------------------
# Streaming testler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_stream_yields_chunks(respx_mock):
    respx_mock.post(f"{BASE_URL}/api/chat").mock(
        return_value=httpx.Response(200, content=_stream_body(STREAM_LINES))
    )
    client = OllamaClient(base_url=BASE_URL, model=MODEL)
    chunks = [chunk async for chunk in client.chat_stream(MESSAGES)]
    assert chunks == ["Sela", "mun", "aleyküm"]
    assert "".join(chunks) == "Selamunaleyküm"


@pytest.mark.asyncio
async def test_chat_stream_raises_on_http_error(respx_mock):
    respx_mock.post(f"{BASE_URL}/api/chat").mock(
        return_value=httpx.Response(503, text="unavailable")
    )
    client = OllamaClient(base_url=BASE_URL, model=MODEL)
    with pytest.raises(OllamaError, match="HTTP hatasi"):
        async for _ in client.chat_stream(MESSAGES):
            pass


@pytest.mark.asyncio
async def test_chat_stream_raises_on_connection_error(respx_mock):
    respx_mock.post(f"{BASE_URL}/api/chat").mock(
        side_effect=httpx.ConnectError("sunucu kapali")
    )
    client = OllamaClient(base_url=BASE_URL, model=MODEL)
    with pytest.raises(OllamaError, match="baglanti hatasi"):
        async for _ in client.chat_stream(MESSAGES):
            pass


# ---------------------------------------------------------------------------
# Payload yapisi testi
# ---------------------------------------------------------------------------


def test_build_payload_non_stream():
    client = OllamaClient(base_url=BASE_URL, model=MODEL)
    payload = client._build_payload(MESSAGES, stream=False)
    assert payload["model"] == MODEL
    assert payload["messages"] == MESSAGES
    assert payload["stream"] is False


def test_build_payload_stream():
    client = OllamaClient(base_url=BASE_URL, model=MODEL)
    payload = client._build_payload(MESSAGES, stream=True)
    assert payload["stream"] is True
