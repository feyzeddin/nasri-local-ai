from __future__ import annotations

from pathlib import Path

import nasri_agent.telegram_setup as tg


def test_telegram_setup_writes_env(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    env_example = repo / "project" / "nasri-core" / ".env.example"
    env_example.parent.mkdir(parents=True, exist_ok=True)
    env_example.write_text("TELEGRAM_ENABLED=0\n", encoding="utf-8")

    monkeypatch.setattr(tg, "install_dir", lambda: repo)
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt="": "123:abc" if "BOT_TOKEN" in prompt else "",
    )

    code = tg.run_telegram_setup()
    assert code == 0

    env_file = repo / "project" / "nasri-core" / ".env"
    text = env_file.read_text(encoding="utf-8")
    assert "TELEGRAM_ENABLED=1" in text
    assert "TELEGRAM_BOT_TOKEN=123:abc" in text
    assert "TELEGRAM_WEBHOOK_SECRET=" in text
