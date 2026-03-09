from __future__ import annotations

import fakeredis.aioredis as fakeredis
import httpx
import pytest

import app.services.federation as f_module


class _Settings:
    federation_enabled = True
    federation_node_id = "node-a"
    federation_shared_token = "shared-secret"


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(f_module, "get_redis", lambda: fake)
    monkeypatch.setattr(f_module, "get_settings", lambda: _Settings())
    return fake


@pytest.mark.asyncio
async def test_register_list_remove_peer():
    out = await f_module.register_peer(
        peer_id="peer-1",
        base_url="http://localhost:9001/",
        token="abc",
    )
    assert out.peer_id == "peer-1"
    assert out.base_url == "http://localhost:9001"
    assert out.has_token is True

    peers = await f_module.list_peers()
    assert len(peers) == 1
    assert peers[0].peer_id == "peer-1"

    deleted = await f_module.remove_peer("peer-1")
    assert deleted is True
    assert await f_module.list_peers() == []


@pytest.mark.asyncio
async def test_dispatch_uses_shared_token_fallback(monkeypatch):
    await f_module.register_peer(
        peer_id="peer-1",
        base_url="http://peer.local",
        token=None,
    )

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"detail": "ok"}

    class _Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, *, json=None, headers=None):
            assert json == {"x": 1}
            assert headers["X-Federation-Token"] == "shared-secret"
            assert headers["X-Federation-Node"] == "node-a"
            return _Resp()

    monkeypatch.setattr(f_module.httpx, "AsyncClient", _Client)
    status_code, detail = await f_module.dispatch_to_peer(
        peer_id="peer-1",
        path="federation/inbox",
        payload={"x": 1},
    )
    assert status_code == 200
    assert detail == "ok"


@pytest.mark.asyncio
async def test_dispatch_handles_request_error(monkeypatch):
    await f_module.register_peer(
        peer_id="peer-2",
        base_url="http://peer.local",
        token="local-token",
    )

    class _Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, *, json=None, headers=None):
            raise httpx.RequestError("down")

    monkeypatch.setattr(f_module.httpx, "AsyncClient", _Client)
    with pytest.raises(f_module.FederationError):
        await f_module.dispatch_to_peer(
            peer_id="peer-2",
            path="/federation/inbox",
            payload={},
        )


def test_verify_shared_token():
    f_module.verify_shared_token("shared-secret")
    with pytest.raises(f_module.FederationError):
        f_module.verify_shared_token("wrong")

