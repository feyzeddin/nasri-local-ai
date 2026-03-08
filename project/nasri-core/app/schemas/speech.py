from __future__ import annotations

from pydantic import BaseModel


class SpeechTranscribeResponse(BaseModel):
    text: str
    language: str
    engine: str


class SpeechSynthesizeRequest(BaseModel):
    text: str


