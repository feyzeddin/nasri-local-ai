from __future__ import annotations

import asyncio
import json
import re

import httpx

from app.core.settings import get_settings


class HomeAutomationError(Exception):
    pass


class HomeAutomationUnavailableError(HomeAutomationError):
    pass


def _normalize(text: str) -> str:
    return " ".join(text.lower().strip().split())


def _detect_action_target(command_text: str) -> tuple[str, str]:
    t = _normalize(command_text)
    target = "generic"
    if any(k in t for k in ["ışık", "isik", "lamba"]):
        target = "light"
    elif any(k in t for k in ["ısı", "isit", "kalorifer", "heater"]):
        target = "climate"
    elif any(k in t for k in ["tv", "televizyon"]):
        target = "media_player"

    if any(k in t for k in ["aç", "ac", "yak"]):
        action = "turn_on"
    elif any(k in t for k in ["kapat", "söndür", "sondur"]):
        action = "turn_off"
    elif target == "climate":
        if "derece" in t or re.search(r"\b\d{2}\b", t):
            action = "set_temperature"
        else:
            action = "turn_on"
    else:
        raise HomeAutomationError("Komuttan eylem çıkarılamadı.")
    return action, target


def _extract_temperature(command_text: str) -> float | None:
    m = re.search(r"\b(\d{2})(?:\s*derece)?\b", _normalize(command_text))
    if not m:
        return None
    return float(m.group(1))


def _mqtt_topic(target: str, action: str) -> str:
    s = get_settings()
    return f"{s.mqtt_topic_prefix}/{target}/{action}"


async def publish_mqtt(target: str, action: str, payload: dict) -> None:
    s = get_settings()
    if not s.mqtt_enabled:
        raise HomeAutomationUnavailableError("MQTT devre dışı.")

    topic = _mqtt_topic(target, action)

    def _pub() -> None:
        try:
            from paho.mqtt import publish  # type: ignore
        except Exception as exc:
            raise HomeAutomationError("paho-mqtt kurulu değil.") from exc

        auth = None
        if s.mqtt_username:
            auth = {"username": s.mqtt_username, "password": s.mqtt_password}
        publish.single(
            topic,
            payload=json.dumps(payload, ensure_ascii=False),
            hostname=s.mqtt_host,
            port=s.mqtt_port,
            auth=auth,
            qos=0,
            retain=False,
        )

    await asyncio.to_thread(_pub)


async def call_home_assistant(target: str, action: str, payload: dict) -> None:
    s = get_settings()
    if not s.home_assistant_enabled:
        raise HomeAutomationUnavailableError("Home Assistant devre dışı.")
    if not s.home_assistant_token:
        raise HomeAutomationError("HOME_ASSISTANT_TOKEN ayarlı değil.")

    domain = "homeassistant"
    service = action
    if target == "light":
        domain = "light"
    elif target == "climate":
        domain = "climate"
    elif target == "media_player":
        domain = "media_player"

    url = f"{s.home_assistant_url.rstrip('/')}/api/services/{domain}/{service}"
    headers = {
        "Authorization": f"Bearer {s.home_assistant_token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HomeAutomationError(f"Home Assistant HTTP hatası: {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise HomeAutomationError(f"Home Assistant bağlantı hatası: {exc}") from exc


async def run_command(command_text: str, mode: str = "auto") -> tuple[str, str, str]:
    action, target = _detect_action_target(command_text)
    payload: dict[str, object] = {"area_id": get_settings().home_assistant_default_area}
    if action == "set_temperature":
        temp = _extract_temperature(command_text)
        if temp is None:
            raise HomeAutomationError("Sıcaklık değeri bulunamadı.")
        payload["temperature"] = temp
        payload["hvac_mode"] = "heat"

    mode_req = mode.lower().strip()
    if mode_req not in {"auto", "mqtt", "ha"}:
        raise HomeAutomationError("Geçersiz mode.")

    if mode_req in {"auto", "ha"}:
        try:
            await call_home_assistant(target, action, payload)
            return "ha", action, target
        except HomeAutomationUnavailableError:
            if mode_req == "ha":
                raise
        except HomeAutomationError:
            if mode_req == "ha":
                raise
    if mode_req in {"auto", "mqtt"}:
        await publish_mqtt(target, action, payload)
        return "mqtt", action, target
    raise HomeAutomationError("Komut işlenemedi.")
