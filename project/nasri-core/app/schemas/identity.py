from __future__ import annotations

from pydantic import BaseModel, Field


class DeviceInfo(BaseModel):
    hostname: str = Field(..., min_length=1, max_length=255)
    os_name: str = Field(..., min_length=1, max_length=100)
    machine_id: str = Field(..., min_length=1, max_length=255)


class IdentityEnrollRequest(BaseModel):
    profile_id: str = Field(..., min_length=1, max_length=100)
    device: DeviceInfo
    biometric_sample: str = Field(..., min_length=1, max_length=4000)


class IdentityVerifyRequest(BaseModel):
    profile_id: str = Field(..., min_length=1, max_length=100)
    device: DeviceInfo
    biometric_sample: str = Field(..., min_length=1, max_length=4000)


class IdentityVerifyResponse(BaseModel):
    profile_id: str
    device_match: bool
    biometric_match: bool
    verified: bool


class IdentityProfileSummary(BaseModel):
    profile_id: str


class IdentityProfileListResponse(BaseModel):
    count: int
    items: list[IdentityProfileSummary]
