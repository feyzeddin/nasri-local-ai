from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import AuthSession, require_roles
from app.schemas.rag import RagIndexRequest, RagIndexResponse, RagQueryResponse
from app.services.rag import RAGError, index_document, query_knowledge

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/index", response_model=RagIndexResponse)
def rag_index(
    body: RagIndexRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> RagIndexResponse:
    try:
        doc_id, chunk_count = index_document(
            body.text,
            document_id=body.document_id,
            source=body.source,
        )
    except RAGError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RagIndexResponse(document_id=doc_id, chunk_count=chunk_count)


@router.get("/query", response_model=RagQueryResponse)
def rag_query(
    q: str = Query(..., min_length=1),
    top_k: int | None = Query(default=None, ge=1, le=20),
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> RagQueryResponse:
    try:
        hits = query_knowledge(q, top_k=top_k)
    except RAGError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RagQueryResponse(query=q, top_k=top_k or len(hits), hits=hits)

