from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ModelRouterChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    system_prompt: str | None = Field(default=None, max_length=4000)
    preferred_tier: Literal["local", "free", "paid"] | None = None


class ModelRouterAttempt(BaseModel):
    tier: str
    status: Literal["ok", "failed", "skipped"]
    detail: str | None = None


class ModelRouterChatResponse(BaseModel):
    reply: str
    used_tier: Literal["local", "free", "paid"]
    attempts: list[ModelRouterAttempt]
