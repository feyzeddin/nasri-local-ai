from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AnomalyEventRequest(BaseModel):
    event_type: Literal["network", "file_access"]
    actor: str = Field(min_length=1, max_length=128)
    source_ip: str | None = None
    destination_ip: str | None = None
    bytes_in: int = Field(default=0, ge=0)
    bytes_out: int = Field(default=0, ge=0)
    path: str | None = None
    operation: str | None = None


class AnomalyIngestResponse(BaseModel):
    anomaly: bool
    severity: Literal["low", "medium", "high"] | None = None
    reason: str | None = None
    alert_id: str | None = None


class AnomalyAlert(BaseModel):
    alert_id: str
    created_at: int
    event_type: str
    actor: str
    severity: str
    reason: str
    details: dict


class AnomalyAlertListResponse(BaseModel):
    count: int
    alerts: list[AnomalyAlert]


class AnomalyStatusResponse(BaseModel):
    enabled: bool
    network_bytes_threshold: int
    network_conn_threshold_per_minute: int
    file_burst_threshold_per_minute: int
