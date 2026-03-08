from __future__ import annotations

from pydantic import BaseModel


class DriverDevice(BaseModel):
    device_id: str
    name: str
    status: str


class DriverScanResponse(BaseModel):
    os_name: str
    device_count: int
    devices: list[DriverDevice]


class DriverInstallRequest(BaseModel):
    device_id: str
    auto_confirm: bool = False


class DriverInstallResponse(BaseModel):
    device_id: str
    installed: bool
    detail: str
