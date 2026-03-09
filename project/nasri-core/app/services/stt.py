from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from app.core.settings import get_settings


class STTError(Exception):
    pass


_TIMESTAMP_RE = re.compile(r"\[[0-9]{2}:[0-9]{2}\.[0-9]{3}\s*-->\s*[0-9]{2}:[0-9]{2}\.[0-9]{3}\]\s*")


def _clean_whisper_output(stdout: str) -> str:
    lines: list[str] = []
    for line in stdout.splitlines():
        text = _TIMESTAMP_RE.sub("", line).strip()
        if text:
            lines.append(text)
    if lines:
        return " ".join(lines).strip()
    return stdout.strip()


def transcribe_audio_bytes(audio_bytes: bytes, suffix: str = ".wav") -> str:
    settings = get_settings()
    if not settings.whisper_cpp_binary:
        raise STTError("WHISPER_CPP_BINARY ayarlı değil.")
    if not settings.whisper_cpp_model:
        raise STTError("WHISPER_CPP_MODEL ayarlı değil.")

    binary = Path(settings.whisper_cpp_binary).expanduser()
    model = Path(settings.whisper_cpp_model).expanduser()
    if not binary.exists():
        raise STTError(f"Whisper.cpp binary bulunamadı: {binary}")
    if not model.exists():
        raise STTError(f"Whisper.cpp model dosyası bulunamadı: {model}")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(audio_bytes)
        tmp.flush()
        cmd = [
            str(binary),
            "-m",
            str(model),
            "-f",
            tmp.name,
            "-l",
            settings.whisper_cpp_language,
            "-nt",
            "-np",
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=settings.whisper_cpp_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise STTError("Whisper.cpp zaman aşımına uğradı.") from exc
        except OSError as exc:
            raise STTError(f"Whisper.cpp çalıştırılamadı: {exc}") from exc

    if proc.returncode != 0:
        raise STTError((proc.stderr or proc.stdout or "Bilinmeyen hata").strip())

    text = _clean_whisper_output(proc.stdout or "")
    if not text:
        raise STTError("Whisper.cpp boş transkript döndürdü.")
    return text

