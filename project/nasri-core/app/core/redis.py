"""Redis bağlantısı ve konuşma geçmişi yönetimi.

Her oturum Redis'te bir liste olarak saklanır:
    key  : conversation:{session_id}
    value: JSON satırları  →  [{"role": "user"|"assistant", "content": "..."}]

Listeye yeni mesajlar sağdan eklenir (RPUSH), okunurken tümü alınır (LRANGE).
Maksimum uzunluk LTRIM ile korunur; key'e TTL atanır.
"""

from __future__ import annotations

import json

import redis.asyncio as aioredis

from app.core.settings import get_settings

# ---------------------------------------------------------------------------
# Bağlantı havuzu — uygulama ömrü boyunca tek örnek
# ---------------------------------------------------------------------------

_pool: aioredis.ConnectionPool | None = None


def _get_pool() -> aioredis.ConnectionPool:
    global _pool
    if _pool is None:
        s = get_settings()
        _pool = aioredis.ConnectionPool.from_url(
            f"redis://{s.redis_host}:{s.redis_port}",
            decode_responses=True,
        )
    return _pool


def get_redis() -> aioredis.Redis:
    """Paylaşımlı havuzdan Redis istemcisi döner."""
    return aioredis.Redis(connection_pool=_get_pool())


# ---------------------------------------------------------------------------
# Oturum geçmişi API'si
# ---------------------------------------------------------------------------

_KEY_PREFIX = "conversation"


def _session_key(session_id: str) -> str:
    return f"{_KEY_PREFIX}:{session_id}"


async def load_history(session_id: str) -> list[dict[str, str]]:
    """Redis'ten oturuma ait tüm mesajları döner.

    Returns:
        [{"role": "user"|"assistant", "content": "..."}] listesi.
        Oturum yoksa boş liste.
    """
    r = get_redis()
    raw: list[str] = await r.lrange(_session_key(session_id), 0, -1)
    messages: list[dict[str, str]] = []
    for item in raw:
        try:
            messages.append(json.loads(item))
        except json.JSONDecodeError:
            continue
    return messages


async def append_messages(
    session_id: str,
    new_messages: list[dict[str, str]],
) -> None:
    """Oturuma yeni mesajları ekler, sınırı uygular ve TTL'i yeniler.

    Args:
        session_id: Oturum kimliği.
        new_messages: Eklenecek mesajlar (sıralı: önce user, sonra assistant).
    """
    if not new_messages:
        return

    s = get_settings()
    max_items = s.max_history_pairs * 2  # her çift: 1 user + 1 assistant
    key = _session_key(session_id)
    r = get_redis()

    pipe = r.pipeline()
    for msg in new_messages:
        pipe.rpush(key, json.dumps(msg, ensure_ascii=False))
    # Sınırı aşan eski mesajları sil (listenin sonundan max_items kadar tut)
    pipe.ltrim(key, -max_items, -1)
    # TTL yenile
    pipe.expire(key, s.session_ttl_seconds)
    await pipe.execute()


async def clear_history(session_id: str) -> None:
    """Oturuma ait tüm geçmişi siler."""
    r = get_redis()
    await r.delete(_session_key(session_id))
