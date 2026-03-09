from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import AuthSession, require_roles
from app.schemas.backup import BackupHistoryItem, BackupHistoryResponse, BackupRunResponse
from app.services.backup import BackupError, backup_history, run_backup

router = APIRouter(prefix="/backup", tags=["backup"])


@router.post("/run", response_model=BackupRunResponse)
async def backup_run(
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> BackupRunResponse:
    try:
        data = await run_backup(trigger="manual")
    except BackupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return BackupRunResponse(**data)


@router.get("/history", response_model=BackupHistoryResponse)
async def backup_list(
    limit: int = Query(default=20, ge=1, le=100),
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> BackupHistoryResponse:
    rows = await backup_history(limit=limit)
    items = [BackupHistoryItem(**x) for x in rows]
    return BackupHistoryResponse(count=len(items), items=items)
