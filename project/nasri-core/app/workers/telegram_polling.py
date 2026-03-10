"""
telegram_polling.py — Telegram long-polling worker.

Public IP / HTTPS olmayan cihazlar için webhook yerine
getUpdates ile mesajları çeker ve messaging_bridge'e iletir.

TELEGRAM_POLLING=1 ve TELEGRAM_BOT_TOKEN ayarlıysa
app startup'ında otomatik başlar.
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from app.core.settings import get_settings
from app.services.messaging_bridge import (
    MessagingError,
    ask_nasri,
    format_command_reply,
    send_telegram_message,
)

logger = logging.getLogger(__name__)

_POLLING_TASK: asyncio.Task | None = None  # type: ignore[type-arg]
_TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def _api(token: str, method: str) -> str:
    return _TELEGRAM_API.format(token=token, method=method)


async def _process_update(client: httpx.AsyncClient, token: str, update: dict) -> None:
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    text = str(message.get("text") or "").strip()
    chat_id = str(chat.get("id") or "")
    external_user_id = str(sender.get("id") or "")

    if not text or not chat_id or not external_user_id:
        return

    command_reply = await format_command_reply("telegram", external_user_id, text)
    if command_reply is not None:
        await send_telegram_message(chat_id, command_reply)
        return

    try:
        reply = await ask_nasri("telegram", external_user_id, text)
    except MessagingError:
        reply = "Bu hesap yetkili değil. Önce /pair komutu ile eşleşme kodu üret."

    await send_telegram_message(chat_id, reply)


async def _polling_loop() -> None:
    s = get_settings()
    token = s.telegram_bot_token
    if not token:
        logger.warning("[telegram-polling] TELEGRAM_BOT_TOKEN ayarlı değil, polling durdu.")
        return

    offset = 0
    logger.info("[telegram-polling] Başlatıldı.")

    async with httpx.AsyncClient(timeout=35.0) as client:
        while True:
            try:
                resp = await client.get(
                    _api(token, "getUpdates"),
                    params={"offset": offset, "timeout": 30, "allowed_updates": ["message"]},
                )
                if resp.status_code != 200:
                    logger.warning("[telegram-polling] getUpdates HTTP %s", resp.status_code)
                    await asyncio.sleep(5)
                    continue

                data = resp.json()
                for update in data.get("result") or []:
                    update_id = update.get("update_id", 0)
                    try:
                        await _process_update(client, token, update)
                    except Exception as exc:
                        logger.error("[telegram-polling] update işleme hatası: %s", exc)
                    offset = max(offset, update_id + 1)

            except asyncio.CancelledError:
                logger.info("[telegram-polling] Durduruldu.")
                break
            except Exception as exc:
                logger.error("[telegram-polling] Beklenmeyen hata: %s", exc)
                await asyncio.sleep(5)


def start_telegram_polling() -> None:
    global _POLLING_TASK
    s = get_settings()
    if not s.telegram_polling or not s.telegram_bot_token:
        return
    if _POLLING_TASK and not _POLLING_TASK.done():
        return
    _POLLING_TASK = asyncio.create_task(_polling_loop())
    logger.info("[telegram-polling] Task oluşturuldu.")


async def stop_telegram_polling() -> None:
    global _POLLING_TASK
    if _POLLING_TASK and not _POLLING_TASK.done():
        _POLLING_TASK.cancel()
        try:
            await _POLLING_TASK
        except asyncio.CancelledError:
            pass
    _POLLING_TASK = None
