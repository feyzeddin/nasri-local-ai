from __future__ import annotations

import fakeredis.aioredis as fakeredis
import pytest

import app.services.backup as b_module


class _Settings:
    backup_enabled = True
    backup_source_paths = ""
    backup_output_dir = ""
    backup_retention_count = 3
    backup_encrypt_enabled = True
    backup_remote_target = ""
    backup_remote_command = ""
    vault_master_key = "backup-master-key"
    vault_key_id = "v1"

    def vault_key_bytes(self) -> bytes:
        import hashlib

        return hashlib.sha256(self.vault_master_key.encode("utf-8")).digest()


@pytest.fixture
def fake_redis(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(b_module, "get_redis", lambda: fake)
    return fake


@pytest.mark.asyncio
async def test_run_backup_encrypted(monkeypatch, tmp_path, fake_redis):
    src = tmp_path / "data"
    src.mkdir()
    (src / "a.txt").write_text("hello", encoding="utf-8")

    s = _Settings()
    s.backup_source_paths = str(src)
    s.backup_output_dir = str(tmp_path / "out")
    monkeypatch.setattr(b_module, "get_settings", lambda: s)

    out = await b_module.run_backup(trigger="test")
    assert out["encrypted"] is True
    assert out["size_bytes"] > 0

    hist = await b_module.backup_history(limit=10)
    assert len(hist) == 1


@pytest.mark.asyncio
async def test_run_backup_disabled(monkeypatch, tmp_path, fake_redis):
    s = _Settings()
    s.backup_enabled = False
    s.backup_source_paths = str(tmp_path)
    s.backup_output_dir = str(tmp_path / "out")
    monkeypatch.setattr(b_module, "get_settings", lambda: s)

    with pytest.raises(b_module.BackupError, match="devre dışı"):
        await b_module.run_backup()
