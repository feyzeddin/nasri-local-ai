from __future__ import annotations

import pytest

import app.services.research as r_module


class _Settings:
    research_searxng_url = "http://localhost:8080"
    research_max_results = 5
    research_fetch_timeout_seconds = 10
    research_save_dir = ".nasri-research-test"
    research_allowed_domains = "wikipedia.org,reuters.com,edu"


@pytest.mark.asyncio
async def test_run_research_filters_domains_and_saves(monkeypatch, tmp_path):
    s = _Settings()
    s.research_save_dir = str(tmp_path)
    monkeypatch.setattr(r_module, "get_settings", lambda: s)

    async def _fake_search(_query: str, max_results: int):
        assert max_results == 3
        return [
            {"title": "A", "url": "https://wikipedia.org/wiki/Nasri", "content": "c1"},
            {"title": "B", "url": "https://spam.example.com/post", "content": "c2"},
        ]

    async def _fake_fetch(_url: str):
        return "Nasri bir yerel yapay zeka asistanıdır. Yerel çalışır. Güvenli bir mimari hedefler."

    monkeypatch.setattr(r_module, "_search_searxng", _fake_search)
    monkeypatch.setattr(r_module, "_fetch_page_text", _fake_fetch)

    items, report_path = await r_module.run_research(
        query="nasri nedir",
        max_results=3,
        save_report=True,
    )
    assert len(items) == 1
    assert items[0].source == "wikipedia.org"
    assert report_path is not None


def test_is_domain_allowed():
    assert r_module._is_domain_allowed("https://wikipedia.org/wiki/Test") is True
    assert r_module._is_domain_allowed("https://foo.bar.edu/page") is True
    assert r_module._is_domain_allowed("https://unknown-domain.xyz") is False
