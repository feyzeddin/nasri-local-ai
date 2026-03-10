from __future__ import annotations

import secrets
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

from .config import install_dir


def _env_file() -> Path:
    return install_dir() / "project" / "nasri-core" / ".env"


def _env_example() -> Path:
    return install_dir() / "project" / "nasri-core" / ".env.example"


def _load_env_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def _upsert(lines: list[str], key: str, value: str) -> list[str]:
    out: list[str] = []
    replaced = False
    prefix = f"{key}="
    for line in lines:
        if line.strip().startswith(prefix):
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"{key}={value}")
    return out


def _ensure_env_file() -> Path:
    env_file = _env_file()
    if env_file.exists():
        return env_file
    example = _env_example()
    env_file.parent.mkdir(parents=True, exist_ok=True)
    if example.exists():
        env_file.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        env_file.write_text("", encoding="utf-8")
    return env_file


def _set_telegram_webhook(bot_token: str, webhook_url: str, secret: str) -> tuple[bool, str]:
    base = f"https://api.telegram.org/bot{bot_token}/setWebhook"
    payload = {
        "url": webhook_url,
        "secret_token": secret,
        "allowed_updates": '["message"]',
    }
    url = base + "?" + urllib.parse.urlencode(payload)
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:  # noqa: S310
            body = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return False, str(exc)
    return True, body[:240]


def _delete_telegram_webhook(bot_token: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/deleteWebhook"
    try:
        with urllib.request.urlopen(url, timeout=10):  # noqa: S310
            pass
    except Exception:
        pass


def _restart_service() -> None:
    import shutil  # noqa: PLC0415

    if shutil.which("systemctl"):
        r = subprocess.run(
            ["sudo", "systemctl", "restart", "nasri.service"],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            print("Nasri servisi yeniden başlatıldı.")
        else:
            print("Servis yeniden başlatılamadı. Manuel çalıştırın:")
            print("  sudo systemctl restart nasri.service")


def run_telegram_setup() -> int:
    print("\nTelegram kurulumu başlatılıyor.")
    print("Bot token almak için @BotFather'a /newbot yazın.\n")

    token = input("TELEGRAM_BOT_TOKEN: ").strip()
    if not token:
        print("Token gerekli. Kurulum iptal edildi.")
        return 1

    print("\nNasri bu cihazda nasıl çalışıyor?")
    print("  1) Polling  — public IP gerekmez (ev sunucusu, VPS olmayan)")
    print("  2) Webhook  — public HTTPS URL gerekli (domain/reverse proxy olan)")
    mode_raw = input("Seçim [1/2, varsayılan 1]: ").strip() or "1"
    use_polling = mode_raw != "2"

    secret = secrets.token_urlsafe(24)

    env_file = _ensure_env_file()
    lines = _load_env_lines(env_file)
    lines = _upsert(lines, "TELEGRAM_ENABLED", "1")
    lines = _upsert(lines, "TELEGRAM_BOT_TOKEN", token)
    lines = _upsert(lines, "TELEGRAM_WEBHOOK_SECRET", secret)
    lines = _upsert(lines, "TELEGRAM_POLLING", "1" if use_polling else "0")
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n.env güncellendi: {env_file}")

    if use_polling:
        # Polling modunda mevcut webhook'u sil
        _delete_telegram_webhook(token)
        print("Mod: Polling (getUpdates) — public IP gerekmez.")
        print("Nasri, Telegram'ı otomatik dinlemeye başlayacak.")
    else:
        public_base = input(
            "Webhook public base URL (ör: https://nasri.example.com): "
        ).strip()
        if not public_base:
            print("URL verilmedi. .env güncellendi ama webhook kurulamadı.")
            print("Elle kurmak için:")
            print(
                f"  curl -s 'https://api.telegram.org/bot{token}/setWebhook"
                f"?url=https://DOMAIN/messaging/telegram/webhook"
                f"&secret_token={secret}'"
            )
        else:
            webhook = public_base.rstrip("/") + "/messaging/telegram/webhook"
            ok, detail = _set_telegram_webhook(token, webhook, secret)
            if ok:
                print(f"Telegram webhook ayarlandı: {webhook}")
            else:
                print(f"Webhook ayarlanamadı: {detail}")

    print("\nKurulum tamamlandı. Servis yeniden başlatılıyor...")
    _restart_service()
    print("\nTest: Telegram'dan botunuza /start veya /help yazın.")
    return 0
