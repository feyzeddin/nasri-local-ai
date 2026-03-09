from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest

import app.services.ssh as ssh_module


class _Settings:
    ssh_connect_timeout_seconds = 10


@pytest.fixture
def fake_redis(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(ssh_module, "get_redis", lambda: fake)
    return fake


@pytest.mark.asyncio
async def test_save_profile_password(monkeypatch, fake_redis):
    monkeypatch.setattr(ssh_module, "get_settings", lambda: _Settings())

    async def _fake_set_secret(name: str, value: str):
        assert name == "ssh:edge-router:password"
        assert value == "secret"
        return "v1"

    monkeypatch.setattr(ssh_module, "set_secret", _fake_set_secret)

    profile = await ssh_module.save_profile(
        profile_name="edge-router",
        host="192.168.1.1",
        port=22,
        username="root",
        auth_method="password",
        password="secret",
    )
    assert profile.profile_name == "edge-router"
    raw = await fake_redis.get("ssh:profile:edge-router")
    assert raw is not None


class _FakeChannel:
    @staticmethod
    def recv_exit_status() -> int:
        return 0


class _FakeStream:
    def __init__(self, text: str) -> None:
        self._text = text
        self.channel = _FakeChannel()

    def read(self) -> bytes:
        return self._text.encode("utf-8")


class _FakeClient:
    def exec_command(self, _command: str, timeout: int):
        assert timeout == 12
        return None, _FakeStream("ok"), _FakeStream("")

    def close(self) -> None:
        return


@pytest.mark.asyncio
async def test_exec_command(monkeypatch):
    async def _fake_get_profile(_name: str):
        return ssh_module.SSHProfile(
            profile_name="srv1",
            host="1.1.1.1",
            port=22,
            username="u",
            auth_method="password",
            password_secret="ssh:srv1:password",
        )

    async def _fake_connect(_profile):
        return _FakeClient()

    monkeypatch.setattr(ssh_module, "get_profile", _fake_get_profile)
    monkeypatch.setattr(ssh_module, "_connect_client", _fake_connect)

    code, out, err = await ssh_module.exec_command("srv1", "uptime", timeout_seconds=12)
    assert code == 0
    assert out == "ok"
    assert err == ""
