from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import AuthSession, require_roles
from app.schemas.test_runner import (
    TestRunnerHistoryResponse,
    TestRunnerResult,
    TestRunnerRunRequest,
    TestRunnerStatusResponse,
)
from app.services.test_runner import (
    TestRunnerError,
    get_last_result,
    list_history,
    run_tests,
)

router = APIRouter(prefix="/test-runner", tags=["test-runner"])


@router.get("/status", response_model=TestRunnerStatusResponse)
async def status(
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> TestRunnerStatusResponse:
    try:
        last = await get_last_result()
    except TestRunnerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TestRunnerStatusResponse(
        enabled=True,
        last_run=TestRunnerResult(**last) if last else None,
    )


@router.get("/history", response_model=TestRunnerHistoryResponse)
async def history(
    limit: int = Query(default=10, ge=1, le=50),
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> TestRunnerHistoryResponse:
    try:
        items = await list_history(limit=limit)
    except TestRunnerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TestRunnerHistoryResponse(
        count=len(items),
        items=[TestRunnerResult(**x) for x in items],
    )


@router.post("/run", response_model=TestRunnerResult)
async def run(
    body: TestRunnerRunRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> TestRunnerResult:
    try:
        out = await run_tests(target=body.target, keyword=body.keyword)
    except TestRunnerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TestRunnerResult(**out)

