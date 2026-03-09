from __future__ import annotations

from datetime import datetime, timezone
import json
import uuid

from app.core.redis import get_redis
from app.core.settings import get_settings

_CANDIDATE_PREFIX = "beta:candidate"
_CANDIDATE_SET = "beta:candidates"
_FEEDBACK_PREFIX = "beta:feedback"
_FEEDBACK_LIST = "beta:feedback:list"


class BetaProgramError(Exception):
    pass


def _candidate_key(candidate_id: str) -> str:
    return f"{_CANDIDATE_PREFIX}:{candidate_id}"


def _feedback_key(feedback_id: str) -> str:
    return f"{_FEEDBACK_PREFIX}:{feedback_id}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_enabled() -> None:
    if not get_settings().beta_program_enabled:
        raise BetaProgramError("Beta program devre dışı.")


def _decode_item(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        out = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(out, dict):
        return None
    return out


async def create_candidate(
    *,
    name: str,
    email: str,
    nda_accepted: bool,
    note: str | None = None,
) -> dict:
    _ensure_enabled()
    normalized_email = email.strip().lower()
    if "@" not in normalized_email:
        raise BetaProgramError("Geçerli bir e-posta girin.")
    candidate_id = str(uuid.uuid4())
    payload = {
        "candidate_id": candidate_id,
        "name": name.strip(),
        "email": normalized_email,
        "nda_accepted": bool(nda_accepted),
        "status": "approved" if nda_accepted else "pending_nda",
        "note": (note or "").strip() or None,
        "created_at": _now_iso(),
    }
    r = get_redis()
    data = json.dumps(payload, ensure_ascii=False)
    pipe = r.pipeline()
    pipe.set(_candidate_key(candidate_id), data)
    pipe.sadd(_CANDIDATE_SET, candidate_id)
    await pipe.execute()
    return payload


async def list_candidates() -> list[dict]:
    _ensure_enabled()
    r = get_redis()
    ids = sorted(str(x) for x in await r.smembers(_CANDIDATE_SET))
    out: list[dict] = []
    for candidate_id in ids:
        item = _decode_item(await r.get(_candidate_key(candidate_id)))
        if item:
            out.append(item)
    return out


async def create_feedback(
    *,
    candidate_id: str,
    score: int,
    text: str,
) -> dict:
    _ensure_enabled()
    r = get_redis()
    candidate = _decode_item(await r.get(_candidate_key(candidate_id)))
    if candidate is None:
        raise BetaProgramError("Aday bulunamadı.")
    feedback_id = str(uuid.uuid4())
    payload = {
        "feedback_id": feedback_id,
        "candidate_id": candidate_id,
        "score": int(score),
        "text": text.strip(),
        "created_at": _now_iso(),
    }
    data = json.dumps(payload, ensure_ascii=False)
    pipe = r.pipeline()
    pipe.set(_feedback_key(feedback_id), data)
    pipe.lpush(_FEEDBACK_LIST, feedback_id)
    pipe.ltrim(_FEEDBACK_LIST, 0, 199)
    await pipe.execute()
    return payload


async def list_feedback(limit: int = 50) -> list[dict]:
    _ensure_enabled()
    clamped = max(1, min(200, int(limit)))
    r = get_redis()
    ids = [str(x) for x in await r.lrange(_FEEDBACK_LIST, 0, clamped - 1)]
    out: list[dict] = []
    for feedback_id in ids:
        item = _decode_item(await r.get(_feedback_key(feedback_id)))
        if item:
            out.append(item)
    return out

