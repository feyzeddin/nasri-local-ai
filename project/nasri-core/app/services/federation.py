from __future__ import annotations

import hmac
import json
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.redis import get_redis
from app.core.settings import get_settings

_FEDERATION_SET_KEY = "federation:peers"
_FEDERATION_PREFIX = "federation:peer"


class FederationError(Exception):
    pass


@dataclass
class FederationPeerRecord:
    peer_id: str
    base_url: str
    token: str

    @property
    def has_token(self) -> bool:
        return bool(self.token.strip())


def _peer_key(peer_id: str) -> str:
    return f"{_FEDERATION_PREFIX}:{peer_id}"


def _ensure_enabled() -> None:
    if not get_settings().federation_enabled:
        raise FederationError("Federation devre dışı.")


def _normalize_base_url(url: str) -> str:
    clean = url.strip()
    if not (clean.startswith("http://") or clean.startswith("https://")):
        raise FederationError("base_url http:// veya https:// ile başlamalı.")
    return clean.rstrip("/")


def _normalize_path(path: str) -> str:
    clean = path.strip()
    if not clean:
        raise FederationError("path boş olamaz.")
    if "://" in clean:
        raise FederationError("path sadece relatif endpoint olmalı.")
    return "/" + clean.lstrip("/")


def verify_shared_token(token: str | None) -> None:
    configured = get_settings().federation_shared_token.strip()
    if not configured:
        raise FederationError("FEDERATION_SHARED_TOKEN ayarlı değil.")
    if token is None or not hmac.compare_digest(token, configured):
        raise FederationError("Geçersiz federation token.")


async def register_peer(*, peer_id: str, base_url: str, token: str | None) -> FederationPeerRecord:
    _ensure_enabled()
    normalized_id = peer_id.strip()
    if not normalized_id:
        raise FederationError("peer_id boş olamaz.")
    record = FederationPeerRecord(
        peer_id=normalized_id,
        base_url=_normalize_base_url(base_url),
        token=(token or "").strip(),
    )

    r = get_redis()
    payload = {
        "peer_id": record.peer_id,
        "base_url": record.base_url,
        "token": record.token,
    }
    pipe = r.pipeline()
    pipe.set(_peer_key(record.peer_id), json.dumps(payload, ensure_ascii=False))
    pipe.sadd(_FEDERATION_SET_KEY, record.peer_id)
    await pipe.execute()
    return record


async def _load_peer(peer_id: str) -> FederationPeerRecord | None:
    r = get_redis()
    raw = await r.get(_peer_key(peer_id))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return FederationPeerRecord(
        peer_id=str(data.get("peer_id") or peer_id),
        base_url=str(data.get("base_url") or "").strip(),
        token=str(data.get("token") or "").strip(),
    )


async def list_peers() -> list[FederationPeerRecord]:
    _ensure_enabled()
    r = get_redis()
    peer_ids = sorted(str(x) for x in await r.smembers(_FEDERATION_SET_KEY))
    peers: list[FederationPeerRecord] = []
    for peer_id in peer_ids:
        item = await _load_peer(peer_id)
        if item is None:
            continue
        peers.append(item)
    return peers


async def remove_peer(peer_id: str) -> bool:
    _ensure_enabled()
    normalized_id = peer_id.strip()
    if not normalized_id:
        raise FederationError("peer_id boş olamaz.")
    r = get_redis()
    deleted = await r.delete(_peer_key(normalized_id))
    await r.srem(_FEDERATION_SET_KEY, normalized_id)
    return bool(deleted)


def _detail_from_response(data: Any) -> str:
    if isinstance(data, dict):
        detail = data.get("detail")
        if isinstance(detail, str):
            return detail
    text = str(data)
    return text[:512]


async def dispatch_to_peer(*, peer_id: str, path: str, payload: dict[str, Any]) -> tuple[int, str]:
    _ensure_enabled()
    record = await _load_peer(peer_id.strip())
    if record is None:
        raise FederationError("Peer bulunamadı.")

    route_path = _normalize_path(path)
    url = f"{record.base_url}{route_path}"
    default_token = get_settings().federation_shared_token.strip()
    token = record.token or default_token
    if not token:
        raise FederationError("Dispatch için token bulunamadı.")

    headers = {
        "X-Federation-Token": token,
        "X-Federation-Node": get_settings().federation_node_id,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.RequestError as exc:
        raise FederationError(f"Peer bağlantı hatası: {exc}") from exc

    try:
        response_data: Any = response.json()
    except ValueError:
        response_data = response.text
    return int(response.status_code), _detail_from_response(response_data)

