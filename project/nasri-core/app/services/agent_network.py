from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import uuid

from app.core.redis import get_redis
from app.core.settings import get_settings
from app.services.memory import recall_memory
from app.services.planner import run_planner

_RUN_PREFIX = "agent_network:run"
_RUN_LIST = "agent_network:runs"


class AgentNetworkError(Exception):
    pass


def _run_key(run_id: str) -> str:
    return f"{_RUN_PREFIX}:{run_id}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_enabled() -> None:
    if not get_settings().agent_network_enabled:
        raise AgentNetworkError("Agent network devre dışı.")


def _normalize_goal(goal: str) -> str:
    normalized = " ".join(goal.strip().split())
    if not normalized:
        raise AgentNetworkError("goal boş olamaz.")
    return normalized


def _decode(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        item = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(item, dict):
        return None
    return item


async def _agent_planner(goal: str, profile_id: str | None) -> dict:
    completed, summary, _steps = run_planner(goal, profile_id=profile_id)
    return {"agent": "planner", "ok": completed, "detail": summary}


async def _agent_memory(goal: str, profile_id: str | None) -> dict:
    if not profile_id:
        return {"agent": "memory", "ok": True, "detail": "profile_id yok, bellek adımı atlandı."}
    try:
        hits = recall_memory(profile_id, goal, top_k=3)
    except Exception as exc:
        return {"agent": "memory", "ok": False, "detail": f"bellek hatası: {exc}"}
    return {"agent": "memory", "ok": True, "detail": f"bellek kaydı: {len(hits)}"}


async def _agent_risk(goal: str) -> dict:
    g = goal.lower()
    risky = any(k in g for k in ["sil", "delete", "rm ", "reset", "drop", "prod"])
    if risky:
        return {"agent": "risk", "ok": True, "detail": "Yüksek riskli anahtar kelime tespit edildi."}
    return {"agent": "risk", "ok": True, "detail": "Kritik risk sinyali tespit edilmedi."}


def _supported_agents() -> set[str]:
    return {"planner", "memory", "risk"}


async def _run_single(agent: str, goal: str, profile_id: str | None) -> dict:
    if agent == "planner":
        return await _agent_planner(goal, profile_id)
    if agent == "memory":
        return await _agent_memory(goal, profile_id)
    if agent == "risk":
        return await _agent_risk(goal)
    raise AgentNetworkError(f"Desteklenmeyen agent: {agent}")


async def run_agent_network(
    *,
    goal: str,
    profile_id: str | None,
    agents: list[str],
    parallel: bool,
) -> dict:
    _ensure_enabled()
    normalized_goal = _normalize_goal(goal)

    selected = [a.strip().lower() for a in agents if a.strip()]
    if not selected:
        raise AgentNetworkError("En az bir agent seçilmelidir.")
    if len(selected) > get_settings().agent_network_max_agents:
        raise AgentNetworkError("Agent sayısı limit üstünde.")
    unsupported = [a for a in selected if a not in _supported_agents()]
    if unsupported:
        raise AgentNetworkError(f"Desteklenmeyen agent(ler): {', '.join(unsupported)}")

    if parallel:
        results = await asyncio.gather(*[_run_single(a, normalized_goal, profile_id) for a in selected])
    else:
        results = []
        for a in selected:
            results.append(await _run_single(a, normalized_goal, profile_id))

    ok_count = sum(1 for x in results if x.get("ok"))
    summary = f"{ok_count}/{len(results)} agent başarılı."
    payload = {
        "run_id": str(uuid.uuid4()),
        "goal": normalized_goal,
        "profile_id": profile_id,
        "parallel": bool(parallel),
        "completed": ok_count == len(results),
        "summary": summary,
        "results": results,
        "created_at": _now_iso(),
    }

    r = get_redis()
    raw = json.dumps(payload, ensure_ascii=False)
    pipe = r.pipeline()
    pipe.set(_run_key(payload["run_id"]), raw)
    pipe.lpush(_RUN_LIST, payload["run_id"])
    pipe.ltrim(_RUN_LIST, 0, 199)
    await pipe.execute()
    return payload


async def get_run(run_id: str) -> dict | None:
    _ensure_enabled()
    return _decode(await get_redis().get(_run_key(run_id)))


async def list_runs(limit: int = 50) -> list[dict]:
    _ensure_enabled()
    clamped = max(1, min(200, int(limit)))
    r = get_redis()
    ids = [str(x) for x in await r.lrange(_RUN_LIST, 0, clamped - 1)]
    out: list[dict] = []
    for run_id in ids:
        item = _decode(await r.get(_run_key(run_id)))
        if item:
            out.append(item)
    return out

