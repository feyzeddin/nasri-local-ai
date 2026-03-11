"""
device_auth.py — Cihaz kimlik doğrulama sistemi.

İlk kurulumda `nasri setup-device` ile:
1. Ed25519 anahtar çifti üretilir
2. 2. faktör kodu Telegram'a (varsa) veya ekrana gönderilir
3. Kullanıcı kodu onaylar → cihaz anahtarı aktif olur

Sonraki tüm işlemler cihaz anahtarıyla imzalanır.
Servis yönetimi sudoers kuralı ile şifresiz çalışır.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import datetime as dt
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .config import data_dir, install_dir


# ------------------------------------------------------------------ #
# Dosya yolları
# ------------------------------------------------------------------ #

def _key_file() -> Path:
    return data_dir() / "device.key"


def _pub_file() -> Path:
    return data_dir() / "device.pub"


def _meta_file() -> Path:
    return data_dir() / "device_meta.json"


# ------------------------------------------------------------------ #
# Anahtar üretimi ve yönetimi
# ------------------------------------------------------------------ #

def device_exists() -> bool:
    return _key_file().exists() and _pub_file().exists()


def _generate_keys() -> tuple[bytes, str]:
    """Ed25519 çifti üretir. (private_pem_bytes, fingerprint) döner."""
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    fingerprint = "SHA256:" + base64.b64encode(
        hashlib.sha256(pub_raw).digest()
    ).decode().rstrip("=")
    return private_pem, pub_raw, fingerprint


def _save_keys(private_pem: bytes, pub_raw: bytes, device_id: str, fingerprint: str) -> None:
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)

    kf = _key_file()
    kf.write_bytes(private_pem)
    kf.chmod(0o600)

    pf = _pub_file()
    pf.write_bytes(pub_raw)
    pf.chmod(0o644)

    _meta_file().write_text(
        json.dumps({
            "device_id": device_id,
            "fingerprint": fingerprint,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _delete_keys() -> None:
    for f in (_key_file(), _pub_file(), _meta_file()):
        f.unlink(missing_ok=True)


def load_meta() -> dict:
    try:
        return json.loads(_meta_file().read_text(encoding="utf-8"))
    except Exception:
        return {}


# ------------------------------------------------------------------ #
# İmzalama
# ------------------------------------------------------------------ #

def sign_data(data: bytes) -> Optional[str]:
    """Veriyi cihaz anahtarıyla imzalar. Base64 döner."""
    if not _key_file().exists():
        return None
    try:
        key = serialization.load_pem_private_key(_key_file().read_bytes(), password=None)
        return base64.b64encode(key.sign(data)).decode()  # type: ignore[arg-type]
    except Exception:
        return None


# ------------------------------------------------------------------ #
# Sudoers
# ------------------------------------------------------------------ #

def setup_sudoers(user: str) -> tuple[bool, str]:
    """Nasrî servis komutları için şifresiz sudo kuralı yazar (root gerekli)."""
    cmds = ", ".join([
        "/usr/bin/systemctl start nasri.service",
        "/usr/bin/systemctl stop nasri.service",
        "/usr/bin/systemctl restart nasri.service",
        "/usr/bin/systemctl status nasri.service",
        "/bin/systemctl start nasri.service",
        "/bin/systemctl stop nasri.service",
        "/bin/systemctl restart nasri.service",
        "/bin/systemctl status nasri.service",
    ])
    content = f"# Nasri — sifresiz servis yonetimi\n{user} ALL=(ALL) NOPASSWD: {cmds}\n"
    target = Path("/etc/sudoers.d/nasri")
    try:
        target.write_text(content, encoding="utf-8")
        target.chmod(0o440)
        return True, str(target)
    except PermissionError:
        return False, "root yetkisi gerekli"
    except Exception as exc:
        return False, str(exc)


# ------------------------------------------------------------------ #
# Telegram 2FA
# ------------------------------------------------------------------ #

def _read_env_value(key: str) -> Optional[str]:
    env_path = install_dir() / "project" / "nasri-core" / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key}="):
            val = stripped.split("=", 1)[1].strip()
            return val if val else None
    return None


def _send_telegram_code(code: str) -> bool:
    import urllib.request, urllib.parse
    bot_token = _read_env_value("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return False
    # Owner chat_id'yi Redis'ten okumak yerine state'ten almaya çalış
    # (kurulum sırasında Redis bağlantısı olmayabilir)
    try:
        state_path = data_dir() / "state.json"
        owner_chat_id = None
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            owner_chat_id = state.get("telegram_owner_chat_id")
        if not owner_chat_id:
            return False
        msg = (
            f"🔐 *Nasrî Cihaz Kurulumu*\n\n"
            f"Doğrulama kodu: `{code}`\n\n"
            f"Bu kodu terminale girin."
        )
        payload = urllib.parse.urlencode({
            "chat_id": owner_chat_id,
            "text": msg,
            "parse_mode": "Markdown",
        }).encode()
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        with urllib.request.urlopen(url, data=payload, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


# ------------------------------------------------------------------ #
# Kurulum sihirbazı
# ------------------------------------------------------------------ #

def run_device_setup() -> int:
    _box("Nasrî Cihaz Kimlik Doğrulama Kurulumu")

    if device_exists():
        meta = load_meta()
        print(f"Bu cihaz zaten kayıtlı:")
        print(f"  Cihaz ID  : {meta.get('device_id', '?')}")
        print(f"  Parmak izi: {meta.get('fingerprint', '?')}")
        print(f"  Tarih     : {meta.get('created_at', '?')[:19]}")
        ans = input("\nYeniden oluşturmak istiyor musunuz? [E/H]: ").strip().upper()
        if ans not in ("E", "EVET"):
            print("İptal edildi.")
            return 0
        _delete_keys()

    # Adım 1: Anahtar üret
    print("\n[1/3] Cihaz anahtarı üretiliyor...")
    device_id = "nasri-" + secrets.token_hex(8)
    private_pem, pub_raw, fingerprint = _generate_keys()
    print(f"  ✓ Parmak izi : {fingerprint}")

    # Adım 2: 2. faktör doğrulama
    print("\n[2/3] İkinci faktör doğrulama...")
    code = "".join(secrets.choice("0123456789") for _ in range(6))
    via_telegram = _send_telegram_code(code)

    if via_telegram:
        print("  Doğrulama kodu Telegram'a gönderildi.")
    else:
        print()
        print("  ╔══════════════════════════════╗")
        print(f"  ║  Doğrulama kodu:  {code}      ║")
        print("  ╚══════════════════════════════╝")
        print()

    entered = input("  Kodu girin: ").strip()
    if entered != code:
        print("  ✗ Hatalı kod. Kurulum iptal edildi.")
        return 1

    print("  ✓ Doğrulama başarılı.")

    # Adım 3: Kaydet + sudoers
    _save_keys(private_pem, pub_raw, device_id, fingerprint)
    print(f"\n[3/3] Şifresiz servis yönetimi yapılandırılıyor...")

    user = (
        os.environ.get("SUDO_USER")
        or os.environ.get("USER")
        or "root"
    )
    ok, detail = setup_sudoers(user)
    if ok:
        print(f"  ✓ Sudoers kuralı eklendi ({detail})")
    else:
        print(f"  ! Sudoers yazılamadı ({detail})")
        print(f"    Root ile çalıştırın: sudo nasri setup-device")

    _box("Cihaz kurulumu tamamlandı!\nBundan sonra Nasrî işlemleri için şifre gerekmez.")
    return 0


def _box(text: str) -> None:
    lines = text.splitlines()
    width = max(len(l) for l in lines) + 4
    border = "═" * width
    print(f"\n╔{border}╗")
    for line in lines:
        pad = width - len(line) - 2
        print(f"║  {line}{' ' * pad}  ║")
    print(f"╚{border}╝\n")
