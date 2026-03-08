from __future__ import annotations

from pydantic import BaseModel, Field


class FederationPeerRegisterRequest(BaseModel):
    peer_id: str = Field(min_length=1, max_length=128)
    base_url: str = Field(min_length=5, max_length=512)
    token: str | None = Field(default=None, max_length=512)


class FederationPeer(BaseModel):
    peer_id: str
    base_url: str
    has_token: bool


class FederationPeerListResponse(BaseModel):
    count: int
    peers: list[FederationPeer]


class FederationDispatchRequest(BaseModel):
    peer_id: str = Field(min_length=1, max_length=128)
    path: str = Field(min_length=1, max_length=256)
    payload: dict = Field(default_factory=dict)


class FederationDispatchResponse(BaseModel):
    peer_id: str
    status_code: int
    detail: str


class FederationInboxRequest(BaseModel):
    source_node_id: str = Field(min_length=1, max_length=128)
    payload: dict = Field(default_factory=dict)


class FederationInboxResponse(BaseModel):
    accepted: bool
    node_id: str
    detail: str
