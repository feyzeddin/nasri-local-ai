import os
from pathlib import Path

from nasri_agent.cli import main


def test_status_command_outputs_expected_message(capsys):
    code = main(["/status"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Selamunaleyküm ben Nasrî" in out


def test_version_reads_version_file(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    version_file = repo / "project" / "VERSION"
    version_file.parent.mkdir(parents=True, exist_ok=True)
    version_file.write_text("9.9.9", encoding="utf-8")

    monkeypatch.setenv("NASRI_INSTALL_DIR", str(repo))
    code = main(["/version"])

    out = capsys.readouterr().out
    assert code == 0
    assert "nasri 9.9.9" in out


def test_help_lists_commands(capsys):
    code = main(["/help"])
    out = capsys.readouterr().out
    assert code == 0
    assert "/status" in out
    assert "/version" in out
    assert "/help" in out
    assert "telegram-setup" in out
