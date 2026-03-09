from __future__ import annotations

import json

from app.core.redis import get_redis
from app.core.settings import get_settings

_LOCALE_PREFIX = "i18n:locale"


class InternationalError(Exception):
    pass


def _locale_key(profile_id: str) -> str:
    return f"{_LOCALE_PREFIX}:{profile_id}"


def _decode(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        out = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(out, dict):
        return None
    return out


def _normalize_locale(locale: str) -> str:
    normalized = locale.strip().lower()
    if normalized not in set(get_settings().supported_locales):
        raise InternationalError("Desteklenmeyen locale.")
    return normalized


async def set_locale(profile_id: str, locale: str) -> dict:
    normalized = _normalize_locale(locale)
    payload = {"profile_id": profile_id.strip(), "locale": normalized}
    await get_redis().set(_locale_key(profile_id), json.dumps(payload, ensure_ascii=False))
    return payload


async def get_locale(profile_id: str) -> dict:
    raw = await get_redis().get(_locale_key(profile_id))
    out = _decode(raw)
    if out is None:
        return {"profile_id": profile_id, "locale": get_settings().default_locale}
    return {"profile_id": profile_id, "locale": str(out.get("locale", get_settings().default_locale))}


async def export_profile_data(profile_id: str, email: str | None = None) -> dict:
    r = get_redis()
    locale = await get_locale(profile_id)
    identity_raw = await r.get(f"identity:profile:{profile_id}")
    conversation = await r.lrange(f"conversation:{profile_id}", 0, -1)
    finetune_ids = await r.smembers("finetune:datasets")

    datasets: list[dict] = []
    for ds_id in finetune_ids:
        ds_raw = await r.get(f"finetune:dataset:{ds_id}")
        ds = _decode(ds_raw)
        if ds and str(ds.get("profile_id")) == profile_id:
            datasets.append(ds)

    candidates: list[dict] = []
    for cid in await r.smembers("beta:candidates"):
        raw = await r.get(f"beta:candidate:{cid}")
        item = _decode(raw)
        if not item:
            continue
        if email and str(item.get("email", "")).strip().lower() != email.strip().lower():
            continue
        candidates.append(item)

    return {
        "profile_id": profile_id,
        "locale": locale["locale"],
        "data": {
            "identity": _decode(identity_raw),
            "conversation": conversation,
            "fine_tuning_datasets": datasets,
            "beta_candidates": candidates,
        },
    }


async def erase_profile_data(profile_id: str, email: str | None = None) -> int:
    r = get_redis()
    deleted = 0
    pipe = r.pipeline()
    pipe.delete(f"identity:profile:{profile_id}")
    pipe.srem("identity:profiles", profile_id)
    pipe.delete(_locale_key(profile_id))
    pipe.delete(f"conversation:{profile_id}")

    dataset_ids = await r.smembers("finetune:datasets")
    for ds_id in dataset_ids:
        raw = await r.get(f"finetune:dataset:{ds_id}")
        item = _decode(raw)
        if item and str(item.get("profile_id")) == profile_id:
            pipe.delete(f"finetune:dataset:{ds_id}")
            pipe.srem("finetune:datasets", ds_id)

    if email:
        email_norm = email.strip().lower()
        candidate_ids = await r.smembers("beta:candidates")
        for cid in candidate_ids:
            raw = await r.get(f"beta:candidate:{cid}")
            item = _decode(raw)
            if item and str(item.get("email", "")).strip().lower() == email_norm:
                pipe.delete(f"beta:candidate:{cid}")
                pipe.srem("beta:candidates", cid)

    results = await pipe.execute()
    for x in results:
        try:
            deleted += int(x)
        except Exception:
            continue
    return deleted

