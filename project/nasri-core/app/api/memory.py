from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import AuthSession, require_roles
from app.schemas.memory import (
    MemoryRecallResponse,
    MemoryRecallResponseItem,
    MemoryStoreRequest,
    MemoryStoreResponse,
)
from app.services.memory import MemoryError, recall_memory, store_memory

router = APIRouter(prefix="/memory", tags=["memory"])


@router.post("/store", response_model=MemoryStoreResponse)
def memory_store(
    body: MemoryStoreRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> MemoryStoreResponse:
    try:
        memory_id = store_memory(body.profile_id, body.text, body.tags)
    except MemoryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return MemoryStoreResponse(memory_id=memory_id, profile_id=body.profile_id)


@router.get("/recall", response_model=MemoryRecallResponse)
def memory_recall(
    profile_id: str = Query(..., min_length=1),
    q: str = Query(..., min_length=1),
    top_k: int | None = Query(default=None, ge=1, le=20),
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> MemoryRecallResponse:
    try:
        items = recall_memory(profile_id, q, top_k=top_k)
    except MemoryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return MemoryRecallResponse(
        profile_id=profile_id,
        query=q,
        top_k=top_k or len(items),
        items=[MemoryRecallResponseItem(**x) for x in items],
    )

