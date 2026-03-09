from __future__ import annotations

import app.services.planner as planner_module


class _Settings:
    planner_max_steps = 6


def test_run_planner_basic(monkeypatch):
    monkeypatch.setattr(planner_module, "get_settings", lambda: _Settings())
    done, summary, steps = planner_module.run_planner("Kullaniciya cevapla")
    assert done is True
    assert "finalize" in summary
    assert len(steps) >= 2


def test_run_planner_with_memory(monkeypatch):
    monkeypatch.setattr(planner_module, "get_settings", lambda: _Settings())
    monkeypatch.setattr(
        planner_module,
        "recall_memory",
        lambda *_args, **_kwargs: [{"text": "feyza local tercih eder"}],
    )
    done, summary, steps = planner_module.run_planner("Kullanici profilini hatirla", profile_id="feyza")
    assert done is True
    assert any(s.action == "recall_memory" for s in steps)
    assert "memory_hint" in summary

