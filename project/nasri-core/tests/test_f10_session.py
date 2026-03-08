"""F10 oturum yönetimi endpoint testleri.

F10.1 — DELETE /chat/{session_id}
F10.2 — GET    /chat/{session_id}/history
F10.3 — POST   /chat/session

Redis: fakeredis ile izole edilir.
Ollama: respx ile mock'lanır (sadece mesaj gönderme testlerinde).
"""

from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response

import app.api.chat as chat_module
import app.core.redis as redis_module
from app.main import app
import app.core.settings as settings_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fake_redis_client(monkeypatch):
    """Tüm testlerde Redis'i fakeredis ile değiştirir."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_module, "get_redis", lambda: fake)
    return fake


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# F10.3 — POST /chat/session
# ---------------------------------------------------------------------------


def test_start_session_generates_uuid(client):
    """session_id verilmezse sunucu UUID üretmeli."""
    resp = client.post("/chat/session", json={})
    assert resp.status_code == 201
    data = resp.json()
    assert "session_id" in data
    assert len(data["session_id"]) == 36  # UUID4 formatı


def test_start_session_uses_provided_id(client):
    """session_id verilirse aynen döndürülmeli."""
    resp = client.post("/chat/session", json={"session_id": "my-session"})
    assert resp.status_code == 201
    assert resp.json()["session_id"] == "my-session"


def test_start_session_stores_custom_prompt(client):
    """Özel system_prompt Redis'e kaydedilmeli."""
    resp = client.post(
        "/chat/session",
        json={"session_id": "sess-sp", "system_prompt": "Sen bir asistansın."},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["system_prompt"] == "Sen bir asistansın."


def test_start_session_returns_global_prompt_when_none(client, monkeypatch):
    """system_prompt verilmezse global env değeri dönmeli."""

    class _FakeSettings:
        ollama_url = "http://localhost:11434"
        model_name = "llama3"
        max_history_pairs = 10
        session_ttl_seconds = 3600
        system_prompt = "Global prompt"

    monkeypatch.setattr(settings_module, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(chat_module, "get_settings", lambda: _FakeSettings())

    resp = client.post("/chat/session", json={})
    assert resp.status_code == 201
    assert resp.json()["system_prompt"] == "Global prompt"


def test_start_session_null_prompt_when_no_env(client, monkeypatch):
    """Hiç system_prompt yoksa None dönmeli."""

    class _FakeSettings:
        ollama_url = "http://localhost:11434"
        model_name = "llama3"
        max_history_pairs = 10
        session_ttl_seconds = 3600
        system_prompt = None

    monkeypatch.setattr(settings_module, "get_settings", lambda: _FakeSettings())

    resp = client.post("/chat/session", json={})
    assert resp.status_code == 201
    assert resp.json()["system_prompt"] is None


# ---------------------------------------------------------------------------
# F10.2 — GET /chat/{session_id}/history
# ---------------------------------------------------------------------------


def test_get_history_empty_for_new_session(client):
    """Yeni oturumda boş liste dönmeli."""
    resp = client.get("/chat/new-sess/history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "new-sess"
    assert data["messages"] == []
    assert data["count"] == 0


async def test_get_history_returns_stored_messages(client, fake_redis_client):
    """Kaydedilmiş mesajlar doğru dönmeli."""
    from app.core.redis import append_messages

    await append_messages(
        "hist-sess",
        [
            {"role": "user", "content": "Merhaba"},
            {"role": "assistant", "content": "Selam!"},
        ],
    )

    resp = client.get("/chat/hist-sess/history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert data["messages"][0]["content"] == "Merhaba"
    assert data["messages"][1]["role"] == "assistant"


# ---------------------------------------------------------------------------
# F10.1 — DELETE /chat/{session_id}
# ---------------------------------------------------------------------------


async def test_delete_session_removes_history(client, fake_redis_client):
    """Silme işlemi geçmişi temizlemeli."""
    from app.core.redis import append_messages, load_history

    await append_messages("del-sess", [{"role": "user", "content": "test"}])

    resp = client.delete("/chat/del-sess")
    assert resp.status_code == 204

    remaining = await load_history("del-sess")
    assert remaining == []


def test_delete_session_idempotent(client):
    """Var olmayan oturum silindiğinde de 204 dönmeli."""
    resp = client.delete("/chat/nonexistent-sess")
    assert resp.status_code == 204


async def test_delete_session_removes_system_prompt(client, fake_redis_client):
    """Silme işlemi oturuma özel sistem mesajını da silmeli."""
    from app.core.redis import append_messages, load_history

    # Oturuma özel sistem mesajı kaydet (sys: prefix)
    await append_messages(
        "sys:sp-sess",
        [{"role": "system", "content": "Özel prompt"}],
    )

    resp = client.delete("/chat/sp-sess")
    assert resp.status_code == 204

    sys_msgs = await load_history("sys:sp-sess")
    assert sys_msgs == []


# ---------------------------------------------------------------------------
# F10.3 — Sistem mesajı Ollama'ya iletiliyor mu?
# ---------------------------------------------------------------------------


@respx.mock
def test_system_prompt_prepended_in_chat(client, monkeypatch):
    """Kaydedilmiş sistem mesajı Ollama isteğine eklenmeli."""
    import json

    captured: list[dict] = []

    class _FakeSettings:
        ollama_url = "http://fake-ollama:11434"
        model_name = "llama3"
        max_history_pairs = 10
        session_ttl_seconds = 3600
        system_prompt = None

    monkeypatch.setattr(settings_module, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(redis_module, "get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(chat_module, "get_settings", lambda: _FakeSettings())

    def capture_request(request):
        captured.append(json.loads(request.content))
        return Response(
            200,
            json={"message": {"content": "Yanıt"}, "done": True},
        )

    respx.post("http://fake-ollama:11434/api/chat").mock(side_effect=capture_request)

    # Önce oturum başlat, sistem mesajı kaydet
    client.post(
        "/chat/session",
        json={"session_id": "sys-test", "system_prompt": "Sen Nasri'sin."},
    )

    # Mesaj gönder
    resp = client.post(
        "/chat",
        json={"message": "Kim sin?", "session_id": "sys-test"},
    )
    assert resp.status_code == 200

    assert len(captured) == 1
    msgs = captured[0]["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == "Sen Nasri'sin."
    assert msgs[-1]["role"] == "user"
    assert msgs[-1]["content"] == "Kim sin?"
