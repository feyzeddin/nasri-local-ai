from __future__ import annotations

import app.services.suggestion as s_module


class _Settings:
    suggestion_enabled = True
    suggestion_max_items = 5


def test_generate_suggestions_from_memory(monkeypatch):
    monkeypatch.setattr(s_module, "get_settings", lambda: _Settings())
    monkeypatch.setattr(
        s_module,
        "recall_memory",
        lambda *_args, **_kwargs: [{"text": "Kullanıcı sabah odaklı çalışmayı seviyor."}],
    )
    items = s_module.generate_proactive_suggestions("feyza")
    assert len(items) >= 1
    assert any("Alışkanlık" in x.title for x in items)


def test_generate_suggestions_disabled(monkeypatch):
    class _Off:
        suggestion_enabled = False
        suggestion_max_items = 5

    monkeypatch.setattr(s_module, "get_settings", lambda: _Off())
    try:
        s_module.generate_proactive_suggestions("feyza")
        assert False, "expected error"
    except s_module.SuggestionError:
        assert True
