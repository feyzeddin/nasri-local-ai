from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone

import httpx

from app.core.redis import append_messages, get_redis, load_history
from app.core.settings import get_settings
from app.services.maintenance import run_maintenance
from app.services.model_router import ModelRouterError, route_chat

_OWNER_KEY = "messaging:owner"
_PAIR_PREFIX = "messaging:pair"
_PAIR_TTL_SECONDS = 600
_SESSION_PREFIX = "bridge"
_ALLOWED_CHANNELS = {"telegram", "whatsapp"}


class MessagingError(Exception):
    pass


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pair_key(code: str) -> str:
    return f"{_PAIR_PREFIX}:{code}"


def _normalize_channel(value: str) -> str:
    ch = value.strip().lower()
    if ch not in _ALLOWED_CHANNELS:
        raise MessagingError("Desteklenmeyen kanal.")
    return ch


def _make_pair_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))


async def start_pairing(channel: str, external_user_id: str, chat_id: str | None = None) -> dict:
    ch = _normalize_channel(channel)
    user = external_user_id.strip()
    if not user:
        raise MessagingError("Kanal kullanıcı kimliği boş olamaz.")

    code = _make_pair_code()
    payload = {
        "channel": ch,
        "external_user_id": user,
        "chat_id": (chat_id or "").strip() or None,
        "created_at": _utc_now_iso(),
    }
    await get_redis().setex(
        _pair_key(code),
        _PAIR_TTL_SECONDS,
        json.dumps(payload, ensure_ascii=False),
    )
    return {
        "pair_code": code,
        "expires_in_seconds": _PAIR_TTL_SECONDS,
    }


async def confirm_pairing(pair_code: str, force_replace_owner: bool = False) -> dict:
    raw = await get_redis().get(_pair_key(pair_code.strip().upper()))
    if not raw:
        raise MessagingError("Pairing code geçersiz veya süresi dolmuş.")
    try:
        pending = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MessagingError("Pairing kaydı bozuk.") from exc

    existing = await get_owner_binding()
    if existing and not force_replace_owner:
        same_channel = existing["channel"] == pending.get("channel")
        same_user = existing["external_user_id"] == pending.get("external_user_id")
        if not (same_channel and same_user):
            raise MessagingError("Sahip zaten eşleşmiş. Değiştirmek için force gerekli.")

    binding = {
        "channel": str(pending.get("channel") or ""),
        "external_user_id": str(pending.get("external_user_id") or ""),
        "chat_id": pending.get("chat_id"),
        "linked_at": _utc_now_iso(),
    }
    if not binding["channel"] or not binding["external_user_id"]:
        raise MessagingError("Pairing kaydı eksik.")

    r = get_redis()
    pipe = r.pipeline()
    pipe.set(_OWNER_KEY, json.dumps(binding, ensure_ascii=False))
    pipe.delete(_pair_key(pair_code.strip().upper()))
    await pipe.execute()
    return binding


async def get_owner_binding() -> dict | None:
    raw = await get_redis().get(_OWNER_KEY)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None

    channel = str(data.get("channel") or "")
    external_user_id = str(data.get("external_user_id") or "")
    if not channel or not external_user_id:
        return None
    return {
        "channel": channel,
        "external_user_id": external_user_id,
        "chat_id": data.get("chat_id"),
        "linked_at": str(data.get("linked_at") or ""),
    }


async def clear_owner_binding() -> bool:
    deleted = await get_redis().delete(_OWNER_KEY)
    return int(deleted) > 0


async def is_owner(channel: str, external_user_id: str) -> bool:
    binding = await get_owner_binding()
    if not binding:
        return False
    return (
        binding["channel"] == _normalize_channel(channel)
        and binding["external_user_id"] == external_user_id.strip()
    )


def _history_as_prompt(messages: list[dict[str, str]], new_message: str) -> str:
    recent = messages[-8:]
    lines: list[str] = []
    for msg in recent:
        role = "Kullanıcı" if msg.get("role") == "user" else "Nasri"
        lines.append(f"{role}: {msg.get('content', '')}")
    lines.append(f"Kullanıcı: {new_message}")
    lines.append("Nasri:")
    return "\n".join(lines)


async def _maybe_run_local_action(text: str) -> str | None:
    lower = text.lower()
    if "bakım" in lower and any(x in lower for x in ("çalıştır", "calistir", "başlat", "baslat")):
        out = await run_maintenance(trigger="messaging")
        status = out.get("updates", {}).get("status", "unknown")
        return f"Bakım çalıştı. update_status={status}"
    if "durum" in lower and "servis" in lower:
        return "Selamunaleyküm ben Nasrî"
    if "sürüm" in lower or "surum" in lower:
        return f"Nasri {get_settings().nasri_version}"
    return None


async def ask_nasri(channel: str, external_user_id: str, text: str) -> str:
    if not await is_owner(channel, external_user_id):
        raise MessagingError("Bu hesap eşleşmiş sahip hesabı değil.")

    message = text.strip()
    if not message:
        raise MessagingError("Boş mesaj gönderilemez.")

    session_id = f"{_SESSION_PREFIX}:{_normalize_channel(channel)}:{external_user_id.strip()}"
    local_action_reply = await _maybe_run_local_action(message)
    if local_action_reply is not None:
        reply = local_action_reply
    else:
        history = await load_history(session_id)
        prompt = _history_as_prompt(history, message)
        try:
            routed = await route_chat(
                prompt=prompt,
                system_prompt=get_settings().system_prompt,
            )
            reply = routed.reply
        except ModelRouterError as exc:
            raise MessagingError(str(exc)) from exc

    await append_messages(
        session_id,
        [
            {"role": "user", "content": message},
            {"role": "assistant", "content": reply},
        ],
    )
    return reply


async def format_command_reply(channel: str, external_user_id: str, text: str) -> str | None:
    content = text.strip()
    lower = content.lower()

    if lower in {"/help", "help"}:
        return (
            "Komutlar:\n"
            "/pair - sahip eşleştirme kodu üret\n"
            "/status - servis durumunu göster\n"
            "/version - sürümü göster\n"
            "/help - komutları listele"
        )

    if lower in {"/status", "status"}:
        return "Selamunaleyküm ben Nasrî"

    if lower in {"/version", "version"}:
        return f"Nasri {get_settings().nasri_version}"

    if lower in {"/pair", "pair"}:
        started = await start_pairing(channel, external_user_id)
        return (
            f"Eşleşme kodun: {started['pair_code']}\n"
            f"{started['expires_in_seconds']} saniye içinde Nasri panelinden onayla."
        )

    return None


async def send_telegram_message(chat_id: str, text: str) -> None:
    s = get_settings()
    if not s.telegram_bot_token:
        raise MessagingError("TELEGRAM_BOT_TOKEN ayarlı değil.")
    payload = {"chat_id": chat_id, "text": text}
    url = f"https://api.telegram.org/bot{s.telegram_bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code >= 400:
            raise MessagingError(f"Telegram gönderim hatası: {resp.status_code}")


async def send_whatsapp_message(to: str, text: str) -> None:
    s = get_settings()
    if not s.whatsapp_access_token or not s.whatsapp_phone_number_id:
        raise MessagingError("WhatsApp API ayarları eksik.")
    url = f"https://graph.facebook.com/v20.0/{s.whatsapp_phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    headers = {
        "Authorization": f"Bearer {s.whatsapp_access_token}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code >= 400:
            raise MessagingError(f"WhatsApp gönderim hatası: {resp.status_code}")
