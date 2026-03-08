from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import urlparse

import httpx

from app.core.settings import get_settings


class ResearchError(Exception):
    pass


@dataclass
class ResearchResultItem:
    title: str
    url: str
    source: str
    summary: str


def _allowed_domains() -> list[str]:
    raw = get_settings().research_allowed_domains
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


def _is_domain_allowed(url: str) -> bool:
    domain = (urlparse(url).hostname or "").lower()
    if not domain:
        return False
    allowed = _allowed_domains()
    for item in allowed:
        if item == "edu":
            if domain.endswith(".edu"):
                return True
            continue
        if domain == item or domain.endswith("." + item):
            return True
    return False


async def _search_searxng(query: str, max_results: int) -> list[dict]:
    s = get_settings()
    base = s.research_searxng_url.rstrip("/")
    params = {"q": query, "format": "json"}
    try:
        async with httpx.AsyncClient(timeout=s.research_fetch_timeout_seconds) as client:
            resp = await client.get(f"{base}/search", params=params)
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ResearchError(f"SearXNG HTTP hatası: {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise ResearchError(f"SearXNG bağlantı hatası: {exc}") from exc

    data = resp.json()
    if not isinstance(data, dict):
        raise ResearchError("SearXNG yanıtı geçersiz.")
    raw_results = data.get("results")
    if not isinstance(raw_results, list):
        return []
    return raw_results[:max_results]


def _strip_html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


async def _fetch_page_text(url: str) -> str:
    s = get_settings()
    try:
        async with httpx.AsyncClient(timeout=s.research_fetch_timeout_seconds) as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
    except Exception:
        return ""
    content_type = resp.headers.get("content-type", "")
    if "text/html" not in content_type and "text/" not in content_type:
        return ""
    return _strip_html(resp.text)


def _summarize(text: str, max_sentences: int = 3) -> str:
    if not text:
        return "Özet çıkarılamadı."
    sentences = re.split(r"(?<=[.!?])\s+", text)
    clean = [s.strip() for s in sentences if len(s.strip()) > 20]
    if not clean:
        return text[:240]
    out = " ".join(clean[:max_sentences]).strip()
    return out[:500]


def _source_name(url: str) -> str:
    return (urlparse(url).hostname or "unknown").lower()


def _report_file_path(query: str) -> Path:
    s = get_settings()
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", query).strip("-").lower()[:48] or "query"
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    root = Path(s.research_save_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return root / f"research-{ts}-{safe}.json"


def _save_report(query: str, items: list[ResearchResultItem]) -> str:
    path = _report_file_path(query)
    payload = {
        "query": query,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "items": [item.__dict__ for item in items],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


async def run_research(
    query: str,
    max_results: int | None = None,
    save_report: bool = True,
) -> tuple[list[ResearchResultItem], str | None]:
    q = " ".join(query.strip().split())
    if not q:
        raise ResearchError("query boş olamaz.")

    s = get_settings()
    limit = max_results or s.research_max_results
    raw = await _search_searxng(q, max_results=limit)

    items: list[ResearchResultItem] = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        url = str(r.get("url", "")).strip()
        title = str(r.get("title", "")).strip() or "Untitled"
        if not url or not _is_domain_allowed(url):
            continue
        page_text = await _fetch_page_text(url)
        summary = _summarize(page_text or str(r.get("content", "")))
        items.append(
            ResearchResultItem(
                title=title,
                url=url,
                source=_source_name(url),
                summary=summary,
            )
        )

    report_path = _save_report(q, items) if save_report else None
    return items, report_path
