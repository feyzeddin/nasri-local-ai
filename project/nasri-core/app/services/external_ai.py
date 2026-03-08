from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any

import httpx

from app.core.redis import get_redis
from app.core.settings import get_settings

_PROVIDERS = ("groq", "gemini", "openrouter")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[- ]?)?(?:\d{3}[- ]?){2}\d{2,4}\b")


class ExternalAIError(Exception):
    pass


class ExternalAIRateLimitError(ExternalAIError):
    pass


@dataclass
class ExternalAIResult:
    provider: str
    model: str
    reply: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    anonymized: bool


def _normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized not in _PROVIDERS:
        raise ExternalAIError("Desteklenmeyen provider.")
    return normalized


def _anonymize_text(text: str) -> tuple[str, bool]:
    masked = _EMAIL_RE.sub("[email]", text)
    masked = _PHONE_RE.sub("[phone]", masked)
    return masked, masked != text


def _provider_limits_and_price(provider: str) -> tuple[int, float, float]:
    s = get_settings()
    if provider == "groq":
        return s.groq_rpm, s.groq_cost_input_per_1k, s.groq_cost_output_per_1k
    if provider == "gemini":
        return s.gemini_rpm, s.gemini_cost_input_per_1k, s.gemini_cost_output_per_1k
    return (
        s.openrouter_rpm,
        s.openrouter_cost_input_per_1k,
        s.openrouter_cost_output_per_1k,
    )


def _provider_config(provider: str) -> tuple[str, str, str]:
    s = get_settings()
    if provider == "groq":
        return s.groq_api_url, s.groq_api_key, s.groq_model
    if provider == "gemini":
        return s.gemini_api_url, s.gemini_api_key, s.gemini_model
    return s.openrouter_api_url, s.openrouter_api_key, s.openrouter_model


async def _rate_limit_guard(provider: str) -> None:
    rpm, _, _ = _provider_limits_and_price(provider)
    if rpm <= 0:
        return
    now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    key = f"external_ai:rate:{provider}:{now}"
    r = get_redis()
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, 120)
    if count > rpm:
        raise ExternalAIRateLimitError(f"{provider} rate limit aşıldı ({rpm}/dk).")


def _estimate_cost_usd(
    input_tokens: int,
    output_tokens: int,
    input_per_1k: float,
    output_per_1k: float,
) -> float:
    return round((input_tokens / 1000.0) * input_per_1k + (output_tokens / 1000.0) * output_per_1k, 8)


async def _track_cost(
    provider: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
) -> None:
    date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"external_ai:cost:{provider}:{date_key}"
    r = get_redis()
    pipe = r.pipeline()
    pipe.hincrby(key, "requests", 1)
    pipe.hincrby(key, "input_tokens", int(input_tokens))
    pipe.hincrby(key, "output_tokens", int(output_tokens))
    pipe.hincrbyfloat(key, "cost_usd", float(cost_usd))
    pipe.expire(key, 60 * 60 * 24 * 60)
    await pipe.execute()


async def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ExternalAIError(f"HTTP hatası: {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise ExternalAIError(f"Bağlantı hatası: {exc}") from exc
    data: Any = resp.json()
    if not isinstance(data, dict):
        raise ExternalAIError("Beklenmeyen yanıt formatı.")
    return data


async def _call_openai_compatible(
    *,
    url: str,
    api_key: str,
    model: str,
    prompt: str,
    system_prompt: str | None,
    provider: str,
) -> tuple[str, int, int, str]:
    if not api_key:
        raise ExternalAIError(f"{provider} API key eksik.")
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    payload = {"model": model, "messages": messages}
    data = await _post_json(
        url,
        payload,
        {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ExternalAIError("Yanıt choices alanı içermiyor.")
    first = choices[0]
    if not isinstance(first, dict):
        raise ExternalAIError("Yanıt choices formatı geçersiz.")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ExternalAIError("Yanıt message alanı geçersiz.")
    reply = message.get("content")
    if not isinstance(reply, str) or not reply.strip():
        raise ExternalAIError("Boş yanıt alındı.")
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    input_tokens = int(usage.get("prompt_tokens", 0))
    output_tokens = int(usage.get("completion_tokens", 0))
    model_name = str(data.get("model") or model)
    return reply, input_tokens, output_tokens, model_name


async def _call_gemini(
    *,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    system_prompt: str | None,
) -> tuple[str, int, int, str]:
    if not api_key:
        raise ExternalAIError("gemini API key eksik.")
    url = f"{base_url.rstrip('/')}/{model}:generateContent?key={api_key}"
    parts = [{"text": prompt}]
    payload: dict[str, Any] = {"contents": [{"parts": parts}]}
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
    data = await _post_json(url, payload, {"Content-Type": "application/json"})

    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ExternalAIError("Gemini candidates alanı boş.")
    content = candidates[0].get("content") if isinstance(candidates[0], dict) else None
    parts_data = content.get("parts") if isinstance(content, dict) else None
    reply = ""
    if isinstance(parts_data, list):
        for part in parts_data:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                reply += part["text"]
    if not reply.strip():
        raise ExternalAIError("Gemini boş yanıt döndü.")

    usage = data.get("usageMetadata") if isinstance(data.get("usageMetadata"), dict) else {}
    input_tokens = int(usage.get("promptTokenCount", 0))
    output_tokens = int(usage.get("candidatesTokenCount", 0))
    return reply, input_tokens, output_tokens, model


async def send_chat(
    *,
    provider: str,
    prompt: str,
    system_prompt: str | None = None,
) -> ExternalAIResult:
    normalized_provider = _normalize_provider(provider)
    clean_prompt = " ".join(prompt.strip().split())
    if not clean_prompt:
        raise ExternalAIError("Mesaj boş olamaz.")

    s = get_settings()
    anonymized = False
    if s.external_ai_anonymize_enabled:
        clean_prompt, anonymized = _anonymize_text(clean_prompt)
        if system_prompt:
            system_prompt, _ = _anonymize_text(system_prompt)

    await _rate_limit_guard(normalized_provider)
    url, api_key, model = _provider_config(normalized_provider)

    if normalized_provider in {"groq", "openrouter"}:
        reply, in_tokens, out_tokens, used_model = await _call_openai_compatible(
            url=url,
            api_key=api_key,
            model=model,
            prompt=clean_prompt,
            system_prompt=system_prompt,
            provider=normalized_provider,
        )
    else:
        reply, in_tokens, out_tokens, used_model = await _call_gemini(
            base_url=url,
            api_key=api_key,
            model=model,
            prompt=clean_prompt,
            system_prompt=system_prompt,
        )

    _, in_per_1k, out_per_1k = _provider_limits_and_price(normalized_provider)
    cost_usd = _estimate_cost_usd(
        input_tokens=in_tokens,
        output_tokens=out_tokens,
        input_per_1k=in_per_1k,
        output_per_1k=out_per_1k,
    )
    await _track_cost(normalized_provider, in_tokens, out_tokens, cost_usd)
    return ExternalAIResult(
        provider=normalized_provider,
        model=used_model,
        reply=reply,
        input_tokens=in_tokens,
        output_tokens=out_tokens,
        cost_usd=cost_usd,
        anonymized=anonymized,
    )
