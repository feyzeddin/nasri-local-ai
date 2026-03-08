from __future__ import annotations

from pydantic import BaseModel, Field


class ZigbeeStatusResponse(BaseModel):
    enabled: bool
    bridge_online: bool
    detail: str


class ZigbeeDevice(BaseModel):
    friendly_name: str
    ieee_address: str | None = None
    model: str | None = None
    vendor: str | None = None
    description: str | None = None


class ZigbeeDeviceListResponse(BaseModel):
    count: int
    devices: list[ZigbeeDevice]


class ZigbeePermitJoinRequest(BaseModel):
    seconds: int = Field(default=60, ge=1, le=300)


class ZigbeePermitJoinResponse(BaseModel):
    accepted: bool
    seconds: int
    detail: str


class ZigbeeActionRequest(BaseModel):
    friendly_name: str = Field(min_length=1, max_length=128)
    action: str = Field(min_length=1, max_length=64)
    value: str | int | float | bool | None = None


class ZigbeeActionResponse(BaseModel):
    accepted: bool
    friendly_name: str
    detail: str
