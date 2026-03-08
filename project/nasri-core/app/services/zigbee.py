from __future__ import annotations

from typing import Any

import httpx

from app.core.settings import get_settings


class ZigbeeError(Exception):
    pass


def _headers() -> dict[str, str]:
    s = get_settings()
    headers = {"Content-Type": "application/json"}
    if s.zigbee2mqtt_api_key:
        headers["Authorization"] = f"Bearer {s.zigbee2mqtt_api_key}"
    return headers


async def _request_json(method: str, path: str, payload: dict | None = None) -> Any:
    s = get_settings()
    if not s.zigbee_enabled:
        raise ZigbeeError("Zigbee bridge devre dışı.")
    base = s.zigbee2mqtt_api_url.rstrip("/")
    url = f"{base}{path}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.request(method, url, headers=_headers(), json=payload)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ZigbeeError(f"zigbee2mqtt HTTP hatası: {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise ZigbeeError(f"zigbee2mqtt bağlantı hatası: {exc}") from exc

    try:
        return response.json()
    except ValueError:
        return {"detail": response.text}


async def bridge_status() -> tuple[bool, str]:
    data = await _request_json("GET", "/api/bridge/state")
    if isinstance(data, dict):
        online = str(data.get("state", "")).lower() in {"online", "started", "ok"}
        return online, str(data.get("state", "unknown"))
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
                "friendly_name": str(item.get("friendly_name", "")),
                "ieee_address": item.get("ieee_address"),
                "model": item.get("definition", {}).get("model")
                if isinstance(item.get("definition"), dict)
                else item.get("model_id"),
                "vendor": item.get("definition", {}).get("vendor")
                if isinstance(item.get("definition"), dict)
                else None,
                "description": item.get("definition", {}).get("description")
                if isinstance(item.get("definition"), dict)
                else None,
            }
        )
    return out


async def permit_join(seconds: int) -> tuple[bool, str]:
    await _request_json("POST", "/api/permit_join", {"value": seconds})
    return True, f"Pairing {seconds} saniye için açıldı."


async def send_device_action(
    friendly_name: str,
    action: str,
    value: str | int | float | bool | None = None,
) -> tuple[bool, str]:
    payload: dict[str, Any] = {action: value if value is not None else True}
    await _request_json("POST", f"/api/device/{friendly_name}/set", payload)
    return True, f"{friendly_name} için {action} komutu gönderildi."
