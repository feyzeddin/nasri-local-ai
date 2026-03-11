from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response

from app.core.security import AuthSession, require_roles
from app.core.settings import get_settings
from app.schemas.messaging import (
    OwnerBindingResponse,
    PairingConfirmRequest,
    PairingStartRequest,
    PairingStartResponse,
)
from app.services.messaging_bridge import (
    MessagingError,
    ask_nasri,
    clear_owner_binding,
    confirm_pairing,
    format_command_reply,
    get_owner_binding,
    send_telegram_message,
    send_whatsapp_message,
    start_pairing,
)

router = APIRouter(prefix="/messaging", tags=["messaging"])


@router.post("/pairings/start", response_model=PairingStartResponse)
async def pairing_start(
    body: PairingStartRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> PairingStartResponse:
    try:
        out = await start_pairing(
            channel=body.channel,
            external_user_id=body.external_user_id,
            chat_id=body.chat_id,
        )
    except MessagingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PairingStartResponse(
        pair_code=out["pair_code"],
        expires_in_seconds=out["expires_in_seconds"],
        instruction="Bu kodu 10 dakika içinde /messaging/pairings/confirm ile onaylayın.",
    )


@router.post("/pairings/confirm", response_model=OwnerBindingResponse)
async def pairing_confirm(
    body: PairingConfirmRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> OwnerBindingResponse:
    try:
        out = await confirm_pairing(
            pair_code=body.pair_code,
            force_replace_owner=body.force_replace_owner,
        )
    except MessagingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return OwnerBindingResponse(**out)


@router.get("/pairings/owner", response_model=OwnerBindingResponse)
async def pairing_owner(
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> OwnerBindingResponse:
    out = await get_owner_binding()
    if not out:
        raise HTTPException(status_code=404, detail="Sahip eşleşmesi bulunamadı.")
    return OwnerBindingResponse(**out)


@router.delete("/pairings/owner")
async def pairing_owner_delete(
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> dict[str, bool]:
    deleted = await clear_owner_binding()
    return {"deleted": deleted}


@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    s = get_settings()
    if not s.telegram_enabled:
        raise HTTPException(status_code=404, detail="Telegram entegrasyonu kapalı.")
    if s.telegram_webhook_secret:
        if x_telegram_bot_api_secret_token != s.telegram_webhook_secret:
            raise HTTPException(status_code=401, detail="Geçersiz Telegram webhook secret.")

    payload = await request.json()
    message = payload.get("message") or {}
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    text = str(message.get("text") or "").strip()
    chat_id = str(chat.get("id") or "")
    external_user_id = str(sender.get("id") or "")
    if not text or not chat_id or not external_user_id:
        return {"ok": True}

    command_reply = await format_command_reply("telegram", external_user_id, text, chat_id=chat_id)
    if command_reply is not None:
        await send_telegram_message(chat_id, command_reply)
        return {"ok": True}

    try:
        reply = await ask_nasri("telegram", external_user_id, text)
    except MessagingError:
        reply = "Bu hesap yetkili değil. Önce /pair komutu ile eşleşme kodu üret."
    await send_telegram_message(chat_id, reply)
    return {"ok": True}


@router.get("/whatsapp/webhook")
async def whatsapp_verify(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
) -> Response:
    s = get_settings()
    if not s.whatsapp_enabled:
        raise HTTPException(status_code=404, detail="WhatsApp entegrasyonu kapalı.")
    if hub_mode != "subscribe" or hub_verify_token != s.whatsapp_verify_token:
        raise HTTPException(status_code=403, detail="Webhook doğrulama başarısız.")
    return Response(content=hub_challenge, media_type="text/plain", status_code=200)


@router.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request) -> dict[str, bool]:
    s = get_settings()
    if not s.whatsapp_enabled:
        raise HTTPException(status_code=404, detail="WhatsApp entegrasyonu kapalı.")

    payload = await request.json()
    entries = payload.get("entry") or []
    for entry in entries:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for msg in value.get("messages") or []:
                if msg.get("type") != "text":
                    continue
                body = str(((msg.get("text") or {}).get("body")) or "").strip()
                external_user_id = str(msg.get("from") or "").strip()
                if not body or not external_user_id:
                    continue

                command_reply = await format_command_reply("whatsapp", external_user_id, body)
                if command_reply is not None:
                    await send_whatsapp_message(external_user_id, command_reply)
                    continue

                try:
                    reply = await ask_nasri("whatsapp", external_user_id, body)
                except MessagingError:
                    reply = "Bu hesap yetkili değil. Önce pair yazarak kod alın."
                await send_whatsapp_message(external_user_id, reply)

    return {"ok": True}

