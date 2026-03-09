from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import AuthSession, require_roles
from app.schemas.anomaly import (
    AnomalyAlert,
    AnomalyAlertListResponse,
    AnomalyEventRequest,
    AnomalyIngestResponse,
    AnomalyStatusResponse,
)
from app.services.anomaly import AnomalyError, detector_status, ingest_event, list_alerts

router = APIRouter(prefix="/anomaly", tags=["anomaly"])


@router.get("/status", response_model=AnomalyStatusResponse)
def anomaly_status(
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> AnomalyStatusResponse:
    return AnomalyStatusResponse(**detector_status())


@router.post("/ingest", response_model=AnomalyIngestResponse)
async def anomaly_ingest(
    body: AnomalyEventRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator")),
) -> AnomalyIngestResponse:
    try:
        result, alert_id = await ingest_event(
            event_type=body.event_type,
            actor=body.actor,
            source_ip=body.source_ip,
            destination_ip=body.destination_ip,
            bytes_in=body.bytes_in,
            bytes_out=body.bytes_out,
            path=body.path,
            operation=body.operation,
        )
    except AnomalyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AnomalyIngestResponse(
        anomaly=result.anomaly,
        severity=result.severity,  # type: ignore[arg-type]
        reason=result.reason,
        alert_id=alert_id,
    )


@router.get("/alerts", response_model=AnomalyAlertListResponse)
async def anomaly_alerts(
    limit: int = Query(default=50, ge=1, le=200),
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> AnomalyAlertListResponse:
    rows = await list_alerts(limit=limit)
    alerts = [AnomalyAlert(**x) for x in rows]
    return AnomalyAlertListResponse(count=len(alerts), alerts=alerts)
