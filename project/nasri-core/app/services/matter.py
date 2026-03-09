from __future__ import annotations

from typing import Any

import httpx

from app.core.settings import get_settings


class MatterError(Exception):
    pass


def _headers() -> dict[str, str]:
    s = get_settings()
    headers = {"Content-Type": "application/json"}
    if s.matter_controller_token:
        headers["Authorization"] = f"Bearer {s.matter_controller_token}"
    return headers


async def _request_json(method: str, path: str, payload: dict | None = None) -> Any:
    s = get_settings()
    if not s.matter_enabled:
        raise MatterError("Matter entegrasyonu devre dışı.")
    base = s.matter_controller_url.rstrip("/")
    url = f"{base}{path}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.request(method, url, headers=_headers(), json=payload)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise MatterError(f"Matter controller HTTP hatası: {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise MatterError(f"Matter controller bağlantı hatası: {exc}") from exc

    try:
        return response.json()
    except ValueError:
        return {"detail": response.text}


async def controller_status() -> tuple[bool, str]:
    data = await _request_json("GET", "/api/status")
    if isinstance(data, dict):
        state = str(data.get("state", "unknown"))
        online = state.lower() in {"online", "ok", "ready"}
        return online, state
    return False, "unknown"


async def list_devices() -> list[dict]:
    data = await _request_json("GET", "/api/devices")
    if not isinstance(data, list):
        return []
    out: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "device_id": str(item.get("device_id") or item.get("id") or ""),
                "name": str(item.get("name") or item.get("label") or ""),
                "device_type": item.get("device_type"),
                "vendor": item.get("vendor"),
                "room": item.get("room"),
            }
        )
    return out


async def pair_device(code: str, network_hint: str | None = None) -> tuple[bool, str]:
    payload: dict[str, Any] = {"code": code.strip()}
    if network_hint:
        payload["network_hint"] = network_hint.strip()
    await _request_json("POST", "/api/pair", payload)
    return True, "Matter/Thread eşleştirme isteği gönderildi."


async def send_action(
    device_id: str,
    action: str,
    value: str | int | float | bool | None = None,
) -> tuple[bool, str]:
    payload: dict[str, Any] = {"action": action}
    if value is not None:
        payload["value"] = value
    await _request_json("POST", f"/api/devices/{device_id}/action", payload)
    return True, f"{device_id} için {action} komutu gönderildi."

