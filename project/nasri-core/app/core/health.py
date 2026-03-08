from __future__ import annotations

from typing import Any

import httpx

from app.core.redis import get_redis
from app.core.settings import get_settings


async def check_redis() -> tuple[bool, str]:
    r = get_redis()
    try:
        await r.ping()
        return True, "ok"
    except Exception as exc:
        return False, f"error:{exc}"


async def check_ollama() -> tuple[bool, str]:
    base = get_settings().ollama_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base}/api/tags")
            resp.raise_for_status()
        return True, "ok"
    except Exception as exc:
        return False, f"error:{exc}"


async def build_readiness() -> dict[str, Any]:
    redis_ok, redis_msg = await check_redis()
    ollama_ok, ollama_msg = await check_ollama()
    status = "ok" if redis_ok and ollama_ok else "degraded"
    return {
        "status": status,
        "checks": {
            "redis": {"ok": redis_ok, "detail": redis_msg},
            "ollama": {"ok": ollama_ok, "detail": ollama_msg},
        },
    }

