from __future__ import annotations

from pydantic import BaseModel, Field


class MatterStatusResponse(BaseModel):
    enabled: bool
    controller_online: bool
    detail: str


class MatterDevice(BaseModel):
    device_id: str
    name: str
    device_type: str | None = None
    vendor: str | None = None
    room: str | None = None


class MatterDeviceListResponse(BaseModel):
    count: int
    devices: list[MatterDevice]


class MatterPairRequest(BaseModel):
    code: str = Field(min_length=4, max_length=64)
    network_hint: str | None = Field(default=None, max_length=128)


class MatterPairResponse(BaseModel):
    accepted: bool
    detail: str


class MatterActionRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=128)
    action: str = Field(min_length=1, max_length=64)
    value: str | int | float | bool | None = None


class MatterActionResponse(BaseModel):
    accepted: bool
    device_id: str
    detail: str

