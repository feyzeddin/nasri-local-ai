from __future__ import annotations

import pytest

import app.services.tts as tts_module


class _Settings:
    def __init__(self, binary: str, model: str) -> None:
        self.piper_binary = binary
        self.piper_model = model
        self.piper_output_sample_rate = 22050
        self.piper_timeout_seconds = 10


def test_synthesize_raises_when_missing_env(monkeypatch):
    monkeypatch.setattr(tts_module, "get_settings", lambda: _Settings("", ""))
    with pytest.raises(tts_module.TTSError):
        tts_module.synthesize_speech("merhaba")


def test_synthesize_runs_piper(monkeypatch, tmp_path):
    binary = tmp_path / "piper.exe"
    model = tmp_path / "tr.onnx"
    binary.write_text("x", encoding="utf-8")
    model.write_text("x", encoding="utf-8")
    monkeypatch.setattr(tts_module, "get_settings", lambda: _Settings(str(binary), str(model)))

    def _fake_run(*args, **kwargs):
        # piper çıktısı oluşturulmuş gibi davran
        out_file = args[0][args[0].index("--output_file") + 1]
        with open(out_file, "wb") as f:
            f.write(b"RIFFdemoWAVE")

        class _Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Proc()

    monkeypatch.setattr(tts_module.subprocess, "run", _fake_run)
    out = tts_module.synthesize_speech("selam")
    assert out.startswith(b"RIFF")

