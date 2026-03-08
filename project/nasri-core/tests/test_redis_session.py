"""Redis konuşma geçmişi testleri.

Gerçek Redis bağlantısı gerekmez; fakeredis kullanılır.
"""

from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest

import app.core.redis as redis_module
from app.core.redis import append_messages, clear_history, load_history


# ---------------------------------------------------------------------------
# Fixture: her test için izole fakeredis örneği
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fake_redis_client(monkeypatch):
    """get_redis()'i fakeredis ile değiştirir."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_module, "get_redis", lambda: fake)
    return fake


# ---------------------------------------------------------------------------
# load_history
# ---------------------------------------------------------------------------


async def test_load_history_returns_empty_for_new_session():
    result = await load_history("sess-new")
    assert result == []


async def test_load_history_returns_stored_messages():
    msgs = [
        {"role": "user", "content": "Merhaba"},
        {"role": "assistant", "content": "Selamunaleyküm"},
    ]
    await append_messages("sess-1", msgs)

    result = await load_history("sess-1")
    assert result == msgs


# ---------------------------------------------------------------------------
# append_messages
# ---------------------------------------------------------------------------


async def test_append_messages_accumulates_across_calls():
    turn1 = [
        {"role": "user", "content": "1. soru"},
        {"role": "assistant", "content": "1. cevap"},
    ]
    turn2 = [
        {"role": "user", "content": "2. soru"},
        {"role": "assistant", "content": "2. cevap"},
    ]
    await append_messages("sess-2", turn1)
    await append_messages("sess-2", turn2)

    result = await load_history("sess-2")
    assert result == turn1 + turn2


async def test_append_messages_trims_to_max_history(monkeypatch):
    """max_history_pairs=2 → max 4 mesaj (2 çift) saklanmalı."""

    class _LimitedSettings:
        redis_host = "localhost"
        redis_port = 6379
        max_history_pairs = 2
        session_ttl_seconds = 3600

    # redis.py'nin kendi get_settings referansını patch'le
    monkeypatch.setattr(redis_module, "get_settings", lambda: _LimitedSettings())

    # 3 tur = 6 mesaj; son 4'ü kalmalı
    for i in range(3):
        await append_messages(
            "sess-trim",
            [
                {"role": "user", "content": f"soru-{i}"},
                {"role": "assistant", "content": f"cevap-{i}"},
            ],
        )

    result = await load_history("sess-trim")
    assert len(result) == 4
    assert result[0]["content"] == "soru-1"
    assert result[-1]["content"] == "cevap-2"


async def test_append_messages_noop_for_empty_list():
    await append_messages("sess-empty", [])
    assert await load_history("sess-empty") == []


# ---------------------------------------------------------------------------
# clear_history
# ---------------------------------------------------------------------------


async def test_clear_history_removes_all_messages():
    await append_messages("sess-clear", [{"role": "user", "content": "test"}])
    await clear_history("sess-clear")
    assert await load_history("sess-clear") == []


async def test_clear_history_noop_for_nonexistent_session():
    # Hata fırlatmamalı
    await clear_history("sess-nonexistent")
