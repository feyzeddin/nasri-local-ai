from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SSHProfileCreateRequest(BaseModel):
    profile_name: str = Field(min_length=1, max_length=128)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=128)
    auth_method: Literal["password", "private_key"]
    password: str | None = Field(default=None, max_length=2048)
    private_key: str | None = None
    private_key_passphrase: str | None = Field(default=None, max_length=2048)


class SSHProfileResponse(BaseModel):
    profile_name: str
    host: str
    port: int
    username: str
    auth_method: Literal["password", "private_key"]


class SSHExecRequest(BaseModel):
    profile_name: str = Field(min_length=1, max_length=128)
    command: str = Field(min_length=1, max_length=8000)
    timeout_seconds: int = Field(default=20, ge=1, le=600)


class SSHExecResponse(BaseModel):
    profile_name: str
    exit_code: int
    stdout: str
    stderr: str


class SSHUploadRequest(BaseModel):
    profile_name: str = Field(min_length=1, max_length=128)
    local_path: str = Field(min_length=1, max_length=2048)
    remote_path: str = Field(min_length=1, max_length=2048)


class SSHDownloadRequest(BaseModel):
    profile_name: str = Field(min_length=1, max_length=128)
    remote_path: str = Field(min_length=1, max_length=2048)
    local_path: str = Field(min_length=1, max_length=2048)


class SSHTransferResponse(BaseModel):
    profile_name: str
    source_path: str
    destination_path: str
    transferred: bool = True
