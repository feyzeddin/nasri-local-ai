from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import AuthSession, require_roles
from app.schemas.fine_tuning import (
    FineTuningDataset,
    FineTuningDatasetCreateRequest,
    FineTuningDatasetListResponse,
    FineTuningJob,
    FineTuningJobListResponse,
    FineTuningJobStartRequest,
)
from app.services.fine_tuning import (
    FineTuningError,
    create_dataset,
    get_job,
    list_datasets,
    list_jobs,
    start_job,
)

router = APIRouter(prefix="/fine-tuning", tags=["fine-tuning"])


@router.post("/datasets", response_model=FineTuningDataset)
async def add_dataset(
    body: FineTuningDatasetCreateRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> FineTuningDataset:
    try:
        out = await create_dataset(
            profile_id=body.profile_id,
            name=body.name,
            source_path=body.source_path,
            format=body.format,
        )
    except FineTuningError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FineTuningDataset(**out)


@router.get("/datasets", response_model=FineTuningDatasetListResponse)
async def datasets(
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> FineTuningDatasetListResponse:
    try:
        items = await list_datasets()
    except FineTuningError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FineTuningDatasetListResponse(count=len(items), items=[FineTuningDataset(**x) for x in items])


@router.post("/jobs/start", response_model=FineTuningJob)
async def job_start(
    body: FineTuningJobStartRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> FineTuningJob:
    try:
        out = await start_job(
            dataset_id=body.dataset_id,
            epochs=body.epochs,
            lora_r=body.lora_r,
            lora_alpha=body.lora_alpha,
            learning_rate=body.learning_rate,
            max_steps=body.max_steps,
            dry_run=body.dry_run,
        )
    except FineTuningError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FineTuningJob(**out)


@router.get("/jobs/{job_id}", response_model=FineTuningJob)
async def job_status(
    job_id: str,
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> FineTuningJob:
    try:
        item = await get_job(job_id)
    except FineTuningError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Job bulunamadı.")
    return FineTuningJob(**item)


@router.get("/jobs", response_model=FineTuningJobListResponse)
async def jobs(
    limit: int = Query(default=50, ge=1, le=200),
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> FineTuningJobListResponse:
    try:
        items = await list_jobs(limit=limit)
    except FineTuningError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FineTuningJobListResponse(count=len(items), items=[FineTuningJob(**x) for x in items])

