from __future__ import annotations

import base64
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.redis import get_redis
from app.core.settings import get_settings


class VaultError(Exception):
    pass


_PREFIX = "vault:secret"


def _key(name: str) -> str:
    return f"{_PREFIX}:{name}"


def _encrypt(value: str) -> dict[str, str]:
    settings = get_settings()
    key = settings.vault_key_bytes()
    aes = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aes.encrypt(nonce, value.encode("utf-8"), None)
    blob = base64.b64encode(nonce + ciphertext).decode("utf-8")
    return {"key_id": settings.vault_key_id, "blob": blob}


def _decrypt(blob: str) -> str:
    settings = get_settings()
    key = settings.vault_key_bytes()
    raw = base64.b64decode(blob.encode("utf-8"))
    if len(raw) < 13:
        raise VaultError("Bozuk vault kaydı.")
    nonce, ciphertext = raw[:12], raw[12:]
    aes = AESGCM(key)
    try:
        plain = aes.decrypt(nonce, ciphertext, None)
    except Exception as exc:
        raise VaultError("Vault çözme hatası. Anahtar uyumsuz olabilir.") from exc
    return plain.decode("utf-8")


async def set_secret(name: str, value: str) -> str:
    payload = _encrypt(value)
    await get_redis().set(_key(name), json.dumps(payload, ensure_ascii=False))
    return payload["key_id"]


async def get_secret(name: str) -> tuple[str, str]:
    raw = await get_redis().get(_key(name))
    if not raw:
        raise VaultError("Kayıt bulunamadı.")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise VaultError("Bozuk vault kaydı.") from exc
    key_id = str(payload.get("key_id", "unknown"))
    blob = payload.get("blob")
    if not isinstance(blob, str):
        raise VaultError("Bozuk vault kaydı.")
    return _decrypt(blob), key_id


async def delete_secret(name: str) -> None:
    await get_redis().delete(_key(name))

