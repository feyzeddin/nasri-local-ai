from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.settings import get_settings


class MemoryError(Exception):
    pass


def _embed_text(text: str) -> list[float]:
    s = get_settings()
    url = s.ollama_url.rstrip("/") + "/api/embeddings"
    payload = {"model": s.rag_embedding_model, "prompt": text}
    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        raise MemoryError(f"Embedding hatası: {exc}") from exc

    emb = data.get("embedding")
    if not isinstance(emb, list) or not emb:
        raise MemoryError("Geçersiz embedding yanıtı.")
    return [float(x) for x in emb]


def _get_collection() -> Any:
    s = get_settings()
    persist_dir = os.path.abspath(s.rag_persist_dir)
    os.makedirs(persist_dir, exist_ok=True)
    try:
        import chromadb
    except Exception as exc:
        raise MemoryError("chromadb bağımlılığı kurulu değil.") from exc

    client = chromadb.PersistentClient(path=persist_dir)
    return client.get_or_create_collection(name=s.memory_collection_name)


def store_memory(profile_id: str, text: str, tags: list[str] | None = None) -> str:
    tags = tags or []
    mem_id = str(uuid.uuid4())
    embedding = _embed_text(text)
    col = _get_collection()
    col.upsert(
        ids=[mem_id],
        documents=[text],
        embeddings=[embedding],
        metadatas=[
            {
                "profile_id": profile_id,
                "tags": ",".join(tags),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
    )
    return mem_id


def recall_memory(profile_id: str, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
    s = get_settings()
    k = top_k or s.memory_default_top_k
    col = _get_collection()
    q_emb = _embed_text(query)

    result = col.query(
        query_embeddings=[q_emb],
        n_results=k,
        where={"profile_id": profile_id},
        include=["documents", "metadatas", "distances"],
    )
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    ids = (result.get("ids") or [[]])[0]

    out: list[dict[str, Any]] = []
    for i, doc in enumerate(docs):
        meta = metas[i] if i < len(metas) and isinstance(metas[i], dict) else {}
        dist = float(dists[i]) if i < len(dists) else 0.0
        tags_raw = str(meta.get("tags", ""))
        out.append(
            {
                "memory_id": str(ids[i]) if i < len(ids) else "",
                "text": doc,
                "score": max(0.0, 1.0 - dist),
                "tags": [t for t in tags_raw.split(",") if t],
            }
        )
    return out

