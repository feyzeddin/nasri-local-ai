from __future__ import annotations

import subprocess
import tempfile
import os
from pathlib import Path

from app.core.settings import get_settings


class TTSError(Exception):
    pass


def synthesize_speech(text: str) -> bytes:
    settings = get_settings()
    if not settings.piper_binary:
        raise TTSError("PIPER_BINARY ayarlı değil.")
    if not settings.piper_model:
        raise TTSError("PIPER_MODEL ayarlı değil.")

    binary = Path(settings.piper_binary).expanduser()
    model = Path(settings.piper_model).expanduser()
    if not binary.exists():
        raise TTSError(f"Piper binary bulunamadı: {binary}")
    if not model.exists():
        raise TTSError(f"Piper model bulunamadı: {model}")

    fd, tmp_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        cmd = [
            str(binary),
            "--model",
            str(model),
            "--output_file",
            tmp_path,
            "--sample_rate",
            str(settings.piper_output_sample_rate),
        ]
        try:
            proc = subprocess.run(
                cmd,
                input=text,
                capture_output=True,
                text=True,
                timeout=settings.piper_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TTSError("Piper TTS zaman aşımına uğradı.") from exc
        except OSError as exc:
            raise TTSError(f"Piper çalıştırılamadı: {exc}") from exc

        if proc.returncode != 0:
            raise TTSError((proc.stderr or proc.stdout or "Bilinmeyen hata").strip())

        wav_bytes = Path(tmp_path).read_bytes()
        if not wav_bytes:
            raise TTSError("Piper boş ses çıktısı üretti.")
        return wav_bytes
    finally:
        Path(tmp_path).unlink(missing_ok=True)
