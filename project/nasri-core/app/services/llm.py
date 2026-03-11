"""Ollama HTTP istemcisi.

Kullanim:
    client = OllamaClient(base_url="http://localhost:11434", model="llama3")

    # Tek seferlik yanit
    reply = await client.chat(messages=[{"role": "user", "content": "Merhaba"}])

    # Streaming yanit
    async for chunk in client.chat_stream(messages=[...]):
        print(chunk, end="", flush=True)
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx


class OllamaError(Exception):
    """Ollama'dan gelen hata veya baglanti sorunu."""


class OllamaClient:
    """Ollama /api/chat endpoint'ini saran asenkron istemci."""

    def __init__(self, base_url: str, model: str, timeout: float | None = None) -> None:
        import os
        self._base_url = base_url.rstrip("/")
        self._model = model
        if timeout is None:
            try:
                timeout = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "180"))
            except ValueError:
                timeout = 180.0
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def chat(self, messages: list[dict[str, str]]) -> str:
        """Ollama'ya istek atar, tam yaniti string olarak dondurur.

        stream=false yerine streaming kullanir; Ollama'nin bellekte tam
        yaniti biriktirmesini onler, daha az bellek tuketir ve daha
        guvenilirdir (ozellikle buyuk modellerde).

        Args:
            messages: [{"role": "user"|"assistant"|"system", "content": "..."}]

        Returns:
            Modelin urettigi yanit metni.

        Raises:
            OllamaError: Baglanti hatasi veya HTTP hatasi durumunda.
        """
        chunks: list[str] = []
        async for chunk in self.chat_stream(messages):
            chunks.append(chunk)
        return "".join(chunks)

    async def chat_stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        """Ollama'ya istek atar, modelin urettigi metin parcalarini akitar.

        Args:
            messages: [{"role": "user"|"assistant"|"system", "content": "..."}]

        Yields:
            Her token/parca icin string.

        Raises:
            OllamaError: Baglanti hatasi veya HTTP hatasi durumunda.
        """
        payload = self._build_payload(messages, stream=True)
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/api/chat",
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        chunk = self._parse_stream_line(line)
                        if chunk:
                            yield chunk
        except httpx.HTTPStatusError as exc:
            raise OllamaError(
                f"Ollama HTTP hatasi: {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise OllamaError(f"Ollama baglanti hatasi: {exc}") from exc

    # ------------------------------------------------------------------
    # Yardimci metodlar
    # ------------------------------------------------------------------

    def _build_payload(
        self, messages: list[dict[str, str]], stream: bool
    ) -> dict[str, Any]:
        return {
            "model": self._model,
            "messages": messages,
            "stream": stream,
        }

    @staticmethod
    def _extract_content(data: Any) -> str:
        """Ollama non-stream yanitindan icerik metnini cikarir."""
        try:
            return data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise OllamaError(f"Beklenmedik Ollama yanit formati: {data}") from exc

    @staticmethod
    def _parse_stream_line(line: str) -> str:
        """Tek bir JSON satirindan token metnini cikarir, bitmisse bos doner."""
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return ""
        if data.get("done"):
            return ""
        try:
            return data["message"]["content"]
        except (KeyError, TypeError):
            return ""
