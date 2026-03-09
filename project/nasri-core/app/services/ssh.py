from __future__ import annotations

import asyncio
from dataclasses import dataclass
import io
import json

from app.core.redis import get_redis
from app.core.settings import get_settings
from app.services.vault import VaultError, delete_secret, get_secret, set_secret


class SSHError(Exception):
    pass


@dataclass
class SSHProfile:
    profile_name: str
    host: str
    port: int
    username: str
    auth_method: str
    password_secret: str | None = None
    private_key_secret: str | None = None
    passphrase_secret: str | None = None


_PROFILE_PREFIX = "ssh:profile"


def _profile_key(profile_name: str) -> str:
    return f"{_PROFILE_PREFIX}:{profile_name}"


def _sanitize_profile_name(profile_name: str) -> str:
    name = profile_name.strip()
    if not name:
        raise SSHError("profile_name boş olamaz.")
    if len(name) > 128:
        raise SSHError("profile_name çok uzun.")
    return name


def _load_private_key(private_key_data: str, passphrase: str | None):
    import paramiko as _paramiko

    key_types = [
        _paramiko.RSAKey,
        _paramiko.Ed25519Key,
        _paramiko.ECDSAKey,
        _paramiko.DSSKey,
    ]
    for key_cls in key_types:
        try:
            return key_cls.from_private_key(
                io.StringIO(private_key_data),
                password=passphrase,
            )
        except Exception:
            continue
    raise SSHError("Private key parse edilemedi.")


async def _connect_client(profile: SSHProfile):
    try:
        import paramiko
    except Exception as exc:
        raise SSHError("paramiko kurulu değil.") from exc

    s = get_settings()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connect_kwargs: dict = {
        "hostname": profile.host,
        "port": profile.port,
        "username": profile.username,
        "timeout": s.ssh_connect_timeout_seconds,
    }

    if profile.auth_method == "password":
        if not profile.password_secret:
            raise SSHError("Password secret eksik.")
        try:
            password, _ = await get_secret(profile.password_secret)
        except VaultError as exc:
            raise SSHError(str(exc)) from exc
        connect_kwargs["password"] = password
    elif profile.auth_method == "private_key":
        if not profile.private_key_secret:
            raise SSHError("Private key secret eksik.")
        try:
            private_key_data, _ = await get_secret(profile.private_key_secret)
            passphrase = None
            if profile.passphrase_secret:
                passphrase, _ = await get_secret(profile.passphrase_secret)
        except VaultError as exc:
            raise SSHError(str(exc)) from exc
        pkey = _load_private_key(private_key_data, passphrase)
        connect_kwargs["pkey"] = pkey
    else:
        raise SSHError("Desteklenmeyen auth_method.")

    try:
        await asyncio.to_thread(client.connect, **connect_kwargs)
    except Exception as exc:
        raise SSHError(f"SSH bağlantı hatası: {exc}") from exc
    return client


async def save_profile(
    *,
    profile_name: str,
    host: str,
    port: int,
    username: str,
    auth_method: str,
    password: str | None = None,
    private_key: str | None = None,
    private_key_passphrase: str | None = None,
) -> SSHProfile:
    name = _sanitize_profile_name(profile_name)
    if auth_method not in {"password", "private_key"}:
        raise SSHError("auth_method geçersiz.")

    password_secret = None
    private_key_secret = None
    passphrase_secret = None

    if auth_method == "password":
        if not password:
            raise SSHError("password zorunlu.")
        password_secret = f"ssh:{name}:password"
        await set_secret(password_secret, password)
    else:
        if not private_key:
            raise SSHError("private_key zorunlu.")
        private_key_secret = f"ssh:{name}:private_key"
        await set_secret(private_key_secret, private_key)
        if private_key_passphrase:
            passphrase_secret = f"ssh:{name}:passphrase"
            await set_secret(passphrase_secret, private_key_passphrase)

    profile = SSHProfile(
        profile_name=name,
        host=host.strip(),
        port=port,
        username=username.strip(),
        auth_method=auth_method,
        password_secret=password_secret,
        private_key_secret=private_key_secret,
        passphrase_secret=passphrase_secret,
    )
    await get_redis().set(_profile_key(name), json.dumps(profile.__dict__, ensure_ascii=False))
    return profile


async def get_profile(profile_name: str) -> SSHProfile:
    name = _sanitize_profile_name(profile_name)
    raw = await get_redis().get(_profile_key(name))
    if not raw:
        raise SSHError("SSH profili bulunamadı.")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SSHError("Bozuk SSH profil verisi.") from exc
    return SSHProfile(**data)


async def delete_profile(profile_name: str) -> None:
    profile = await get_profile(profile_name)
    await get_redis().delete(_profile_key(profile.profile_name))
    if profile.password_secret:
        await delete_secret(profile.password_secret)
    if profile.private_key_secret:
        await delete_secret(profile.private_key_secret)
    if profile.passphrase_secret:
        await delete_secret(profile.passphrase_secret)


async def exec_command(
    profile_name: str,
    command: str,
    timeout_seconds: int,
) -> tuple[int, str, str]:
    profile = await get_profile(profile_name)
    client = await _connect_client(profile)
    
    def _run() -> tuple[int, str, str]:
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout_seconds)
        _ = stdin
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        exit_code = int(stdout.channel.recv_exit_status())
        return exit_code, out, err

    try:
        return await asyncio.to_thread(_run)
    except Exception as exc:
        raise SSHError(f"Komut yürütme hatası: {exc}") from exc
    finally:
        client.close()


async def upload_file(profile_name: str, local_path: str, remote_path: str) -> None:
    profile = await get_profile(profile_name)
    client = await _connect_client(profile)

    def _run() -> None:
        sftp = client.open_sftp()
        try:
            sftp.put(local_path, remote_path)
        finally:
            sftp.close()

    try:
        await asyncio.to_thread(_run)
    except Exception as exc:
        raise SSHError(f"Dosya yükleme hatası: {exc}") from exc
    finally:
        client.close()


async def download_file(profile_name: str, remote_path: str, local_path: str) -> None:
    profile = await get_profile(profile_name)
    client = await _connect_client(profile)

    def _run() -> None:
        sftp = client.open_sftp()
        try:
            sftp.get(remote_path, local_path)
        finally:
            sftp.close()

    try:
        await asyncio.to_thread(_run)
    except Exception as exc:
        raise SSHError(f"Dosya indirme hatası: {exc}") from exc
    finally:
        client.close()
