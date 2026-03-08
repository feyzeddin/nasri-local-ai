from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HomeAutomationCommandRequest(BaseModel):
    command_text: str = Field(min_length=1, max_length=4000)
    mode: Literal["auto", "mqtt", "ha"] = "auto"


class HomeAutomationCommandResponse(BaseModel):
    mode_used: Literal["mqtt", "ha"]
    action: str
    target: str
    detail: str
