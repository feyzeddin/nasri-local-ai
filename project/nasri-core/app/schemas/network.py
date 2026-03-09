from __future__ import annotations

from pydantic import BaseModel, Field


class NetworkDiscoverRequest(BaseModel):
    target_cidr: str | None = Field(
        default=None,
        description="Örn: 192.168.1.0/24. Verilmezse varsayılan CIDR kullanılır.",
    )
    include_mdns: bool = True


class NetworkDevice(BaseModel):
    ip: str
    hostname: str | None = None
    source: str
    ownership_score: int
    ownership_label: str


class NetworkDiscoverResponse(BaseModel):
    target_cidr: str
    device_count: int
    devices: list[NetworkDevice]
