from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.security import AuthSession, require_roles
from app.core.settings import get_settings
from app.schemas.speech import SpeechTranscribeResponse
from app.services.stt import STTError, transcribe_audio_bytes

router = APIRouter(prefix="/speech", tags=["speech"])


@router.post("/transcribe", response_model=SpeechTranscribeResponse)
async def transcribe(
    audio: UploadFile = File(...),
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> SpeechTranscribeResponse:
    if audio.content_type is None or not audio.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Ses dosyası yüklemelisiniz.")

    payload = await audio.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Boş dosya gönderildi.")

    suffix = ""
    if audio.filename and "." in audio.filename:
        suffix = "." + audio.filename.split(".")[-1]
    suffix = suffix or ".wav"

    try:
        text = transcribe_audio_bytes(payload, suffix=suffix)
    except STTError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return SpeechTranscribeResponse(
        text=text,
        language=get_settings().whisper_cpp_language,
        engine="whisper.cpp",
    )

