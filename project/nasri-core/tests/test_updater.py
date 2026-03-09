from __future__ import annotations

import json
from pathlib import Path

import nasri_agent.updater as upd


def _prepare_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True, exist_ok=True)
    (repo / "project" / "nasri-core").mkdir(parents=True, exist_ok=True)
    (repo / "project" / "nasri-core" / "requirements.txt").write_text(
        "httpx==0.28.1\n", encoding="utf-8"
    )
    (repo / "project" / "nasri-core" / ".env.example").write_text(
        "A=1\nB=2\n", encoding="utf-8"
    )
    (repo / "project" / "nasri-core" / ".env").write_text("A=1\n", encoding="utf-8")
    (repo / "project" / "UPDATE_MANIFEST.json").write_text(
        json.dumps(
            {
                "dependencies": {
                    "python_requirements": "project/nasri-core/requirements.txt",
                    "editable_packages": ["project/nasri-core"],
                },
                "post_update_commands": [],
            }
        ),
        encoding="utf-8",
    )
    return repo


def test_maybe_update_uses_manifest_and_syncs_env(tmp_path, monkeypatch):
    repo = _prepare_repo(tmp_path)
    monkeypatch.setattr(upd, "install_dir", lambda: repo)
    monkeypatch.setattr(upd, "state_file", lambda: tmp_path / "state.json")
    monkeypatch.setattr(upd, "local_version", lambda: "0.2.0")

    calls: list[list[str]] = []

    def _fake_run(args, cwd=None):
        calls.append(args)
        if args[:4] == ["git", "fetch", "origin", "main"]:
            return 0, ""
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return 0, "abc"
        if args[:3] == ["git", "rev-parse", "origin/main"]:
            return 0, "def"
        if args[:5] == ["git", "pull", "--ff-only", "origin", "main"]:
            return 0, ""
        if args[:4] == [upd.sys.executable, "-m", "pip", "install"]:
            return 0, ""
        return 0, ""

    monkeypatch.setattr(upd, "_run", _fake_run)

    changed = upd.maybe_update()
    assert changed is True
    env_text = (repo / "project" / "nasri-core" / ".env").read_text(encoding="utf-8")
    assert "B=2" in env_text
    assert any(cmd[:5] == ["git", "pull", "--ff-only", "origin", "main"] for cmd in calls)


def test_should_check_update():
    assert upd.should_check_update(None, 24) is True
