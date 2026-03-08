from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.settings import get_settings
from app.services.llm import OllamaClient, OllamaError

_ALLOWED_TIERS = ("local", "free", "paid")


@dataclass
class RouterAttempt:
    tier: str
    status: str
    detail: str | None = None


@dataclass
class RouterResult:
    reply: str
    used_tier: str
    attempts: list[RouterAttempt]


class ModelRouterError(Exception):
    pass


def _normalize_tier_order(raw: str) -> list[str]:
    tiers: list[str] = []
    for part in raw.split(","):
        tier = part.strip().lower()
        if tier in _ALLOWED_TIERS and tier not in tiers:
            tiers.append(tier)
    if not tiers:
        return ["local", "free", "paid"]
    return tiers


async def _chat_local(messages: list[dict[str, str]]) -> str:
    s = get_settings()
    client = OllamaClient(base_url=s.ollama_url, model=s.model_name)
    try:
        return await client.chat(messages)
    except OllamaError as exc:
        raise ModelRouterError(str(exc)) from exc


async def _chat_remote(
    *,
    url: str,
    model: str,
    api_key: str,
    messages: list[dict[str, str]],
) -> str:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {"model": model, "messages": messages}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ModelRouterError(f"HTTP hatası: {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise ModelRouterError(f"Bağlantı hatası: {exc}") from exc

    data: Any = resp.json()
    if isinstance(data, dict):
        # OpenAI-benzeri yanit
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                msg = first.get("message")
                if isinstance(msg, dict):
                    content = msg.get("content")
                    if isinstance(content, str) and content.strip():
                        return content
        # Basit custom yanit
        reply = data.get("reply")
        if isinstance(reply, str) and reply.strip():
            return reply
    raise ModelRouterError("Beklenmeyen yanıt formatı.")


def _build_messages(prompt: str, system_prompt: str | None = None) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    return messages


async def route_chat(
    *,
    prompt: str,
    system_prompt: str | None = None,
    preferred_tier: str | None = None,
) -> RouterResult:
    text = " ".join(prompt.strip().split())
    if not text:
        raise ModelRouterError("Mesaj boş olamaz.")

    s = get_settings()
    order = _normalize_tier_order(s.model_router_tier_order)
    if preferred_tier:
        preferred = preferred_tier.strip().lower()
        if preferred in _ALLOWED_TIERS:
            order = [preferred, *[x for x in order if x != preferred]]
        else:
            raise ModelRouterError("preferred_tier geçersiz.")

    messages = _build_messages(prompt=text, system_prompt=system_prompt)
    attempts: list[RouterAttempt] = []

    for tier in order:
        if tier == "local":
            try:
                reply = await _chat_local(messages)
                attempts.append(RouterAttempt(tier="local", status="ok"))
                return RouterResult(reply=reply, used_tier="local", attempts=attempts)
            except ModelRouterError as exc:
                attempts.append(
                    RouterAttempt(tier="local", status="failed", detail=str(exc))
                )
                continue

        if tier == "free":
            if not s.model_router_free_enabled:
                attempts.append(
                    RouterAttempt(
                        tier="free", status="skipped", detail="free katmanı kapalı"
                    )
                )
                continue
            if not s.model_router_free_api_url or not s.model_router_free_model:
                attempts.append(
                    RouterAttempt(
                        tier="free",
                        status="skipped",
                        detail="free API ayarları eksik",
                    )
                )
                continue
            try:
                reply = await _chat_remote(
                    url=s.model_router_free_api_url,
                    model=s.model_router_free_model,
                    api_key=s.model_router_free_api_key,
                    messages=messages,
                )
                attempts.append(RouterAttempt(tier="free", status="ok"))
                return RouterResult(reply=reply, used_tier="free", attempts=attempts)
            except ModelRouterError as exc:
                attempts.append(
                    RouterAttempt(tier="free", status="failed", detail=str(exc))
                )
                continue

        if tier == "paid":
            if not s.model_router_paid_enabled:
                attempts.append(
                    RouterAttempt(
                        tier="paid", status="skipped", detail="paid katmanı kapalı"
                    )
                )
                continue
            if not s.model_router_paid_api_url or not s.model_router_paid_model:
                attempts.append(
                    RouterAttempt(
                        tier="paid",
                        status="skipped",
                        detail="paid API ayarları eksik",
                    )
                )
                continue
            try:
                reply = await _chat_remote(
                    url=s.model_router_paid_api_url,
                    model=s.model_router_paid_model,
                    api_key=s.model_router_paid_api_key,
                    messages=messages,
                )
                attempts.append(RouterAttempt(tier="paid", status="ok"))
                return RouterResult(reply=reply, used_tier="paid", attempts=attempts)
            except ModelRouterError as exc:
                attempts.append(
                    RouterAttempt(tier="paid", status="failed", detail=str(exc))
                )
                continue

    details = "; ".join(
        f"{a.tier}:{a.status}" + (f"({a.detail})" if a.detail else "") for a in attempts
    )
    raise ModelRouterError(f"Uygun model katmanı bulunamadı. {details}")
