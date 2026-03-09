from __future__ import annotations

import hashlib
import hmac
import json

from app.core.redis import get_redis
from app.core.settings import get_settings
from app.schemas.identity import DeviceInfo, IdentityVerifyResponse

_PREFIX = "identity:profile"
_INDEX_KEY = "identity:profiles"


class IdentityError(Exception):
    pass


def _key(profile_id: str) -> str:
    return f"{_PREFIX}:{profile_id}"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_device_fingerprint(device: DeviceInfo) -> str:
    s = get_settings()
    payload = "|".join(
        [
            s.device_fingerprint_salt,
            device.hostname.strip().lower(),
            device.os_name.strip().lower(),
            device.machine_id.strip().lower(),
        ]
    )
    return _sha256(payload)


def make_biometric_template(sample: str) -> str:
    s = get_settings()
    payload = f"{s.biometric_salt}|{sample.strip()}"
    return _sha256(payload)


async def enroll_identity(profile_id: str, device: DeviceInfo, biometric_sample: str) -> None:
    record = {
        "profile_id": profile_id,
        "device_fingerprint": make_device_fingerprint(device),
        "biometric_template": make_biometric_template(biometric_sample),
    }
    r = get_redis()
    pipe = r.pipeline()
    pipe.set(_key(profile_id), json.dumps(record, ensure_ascii=False))
    pipe.sadd(_INDEX_KEY, profile_id)
    await pipe.execute()


async def verify_identity(
    profile_id: str, device: DeviceInfo, biometric_sample: str
) -> IdentityVerifyResponse:
    raw = await get_redis().get(_key(profile_id))
    if not raw:
        raise IdentityError("Profil bulunamadı.")
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IdentityError("Bozuk kimlik kaydı.") from exc

    stored_device = str(record.get("device_fingerprint", ""))
    stored_bio = str(record.get("biometric_template", ""))

    now_device = make_device_fingerprint(device)
    now_bio = make_biometric_template(biometric_sample)

    device_match = hmac.compare_digest(stored_device, now_device)
    biometric_match = hmac.compare_digest(stored_bio, now_bio)
    verified = device_match and biometric_match
    return IdentityVerifyResponse(
        profile_id=profile_id,
        device_match=device_match,
        biometric_match=biometric_match,
        verified=verified,
    )


async def list_profiles() -> list[str]:
    profiles = await get_redis().smembers(_INDEX_KEY)
    return sorted(str(x) for x in profiles)


async def delete_profile(profile_id: str) -> bool:
    r = get_redis()
    pipe = r.pipeline()
    pipe.delete(_key(profile_id))
    pipe.srem(_INDEX_KEY, profile_id)
    out = await pipe.execute()
    deleted = int(out[0]) if out and len(out) > 0 else 0
    return deleted > 0
