from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ExternalAIChatRequest(BaseModel):
    provider: Literal["groq", "gemini", "openrouter"]
    message: str = Field(min_length=1, max_length=8000)
    system_prompt: str | None = Field(default=None, max_length=4000)


class ExternalAIUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    cost_usd: float


class ExternalAIChatResponse(BaseModel):
    provider: Literal["groq", "gemini", "openrouter"]
    model: str
    reply: str
    anonymized: bool
    usage: ExternalAIUsage
