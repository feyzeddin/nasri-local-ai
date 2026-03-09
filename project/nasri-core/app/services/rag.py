from __future__ import annotations

import os
import uuid
from typing import Any

import httpx

from app.core.settings import get_settings


class RAGError(Exception):
    pass


def _split_chunks(text: str, max_len: int = 1000) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    parts = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
    chunks: list[str] = []
    for part in parts:
        if len(part) <= max_len:
            chunks.append(part)
            continue
        for i in range(0, len(part), max_len):
            chunks.append(part[i : i + max_len].strip())
    return [c for c in chunks if c]


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
        raise RAGError(f"Embedding hatası: {exc}") from exc

    emb = data.get("embedding")
    if not isinstance(emb, list) or not emb:
        raise RAGError("Geçersiz embedding yanıtı.")
    return [float(x) for x in emb]


def _get_collection() -> Any:
    s = get_settings()
    persist_dir = os.path.abspath(s.rag_persist_dir)
    os.makedirs(persist_dir, exist_ok=True)
    try:
        import chromadb  # lazy import
    except Exception as exc:
        raise RAGError("chromadb bağımlılığı kurulu değil.") from exc

    client = chromadb.PersistentClient(path=persist_dir)
    return client.get_or_create_collection(name=s.rag_collection_name)


def index_document(text: str, document_id: str | None = None, source: str | None = None) -> tuple[str, int]:
    chunks = _split_chunks(text)
    if not chunks:
        raise RAGError("İndekslenecek metin boş.")
    doc_id = document_id or str(uuid.uuid4())
    col = _get_collection()

    ids: list[str] = []
    embeddings: list[list[float]] = []
    metadatas: list[dict[str, str]] = []
    for i, chunk in enumerate(chunks):
        chunk_id = f"{doc_id}:{i}"
        ids.append(chunk_id)
        embeddings.append(_embed_text(chunk))
        metadatas.append(
            {
                "document_id": doc_id,
                "chunk_id": chunk_id,
                "source": source or "",
            }
        )

    col.upsert(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas)
    return doc_id, len(chunks)


def query_knowledge(query: str, top_k: int | None = None) -> list[dict[str, Any]]:
    s = get_settings()
    k = top_k or s.rag_default_top_k
    col = _get_collection()
    q_emb = _embed_text(query)

    result = col.query(
        query_embeddings=[q_emb],
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )

    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]

    hits: list[dict[str, Any]] = []
    for i, doc in enumerate(docs):
        dist = float(dists[i]) if i < len(dists) else 0.0
        meta = metas[i] if i < len(metas) and isinstance(metas[i], dict) else {}
        hits.append(
            {
                "text": doc,
                "score": max(0.0, 1.0 - dist),
                "source": meta.get("source") or None,
                "chunk_id": meta.get("chunk_id") or None,
            }
        )
    return hits

