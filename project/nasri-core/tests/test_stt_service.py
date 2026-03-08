from __future__ import annotations

from pathlib import Path

import pytest

import app.services.stt as stt_module


class _Settings:
    def __init__(self, binary: str, model: str) -> None:
        self.whisper_cpp_binary = binary
        self.whisper_cpp_model = model
        self.whisper_cpp_language = "tr"
        self.whisper_cpp_timeout_seconds = 30


def test_clean_whisper_output_removes_timestamps():
    raw = "[00:00.000 --> 00:01.000] merhaba\n[00:01.000 --> 00:02.000] dunya"
    assert stt_module._clean_whisper_output(raw) == "merhaba dunya"


def test_transcribe_raises_when_env_missing(monkeypatch):
    monkeypatch.setattr(stt_module, "get_settings", lambda: _Settings("", ""))
    with pytest.raises(stt_module.STTError):
        stt_module.transcribe_audio_bytes(b"abc")


def test_transcribe_runs_binary(monkeypatch, tmp_path):
    binary = tmp_path / "main.exe"
    model = tmp_path / "ggml-base.bin"
    binary.write_text("x", encoding="utf-8")
    model.write_text("x", encoding="utf-8")
    monkeypatch.setattr(stt_module, "get_settings", lambda: _Settings(str(binary), str(model)))

    class _Proc:
        returncode = 0
        stdout = "[00:00.000 --> 00:01.000] selam"
        stderr = ""

    def _fake_run(*args, **kwargs):
        cmd = args[0]
        assert str(binary) in cmd
        assert str(model) in cmd
        return _Proc()

    monkeypatch.setattr(stt_module.subprocess, "run", _fake_run)
    out = stt_module.transcribe_audio_bytes(b"RIFF....WAVE", suffix=".wav")
    assert out == "selam"

