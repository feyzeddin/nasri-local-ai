from __future__ import annotations

import secrets
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


def run_telegram_setup() -> int:
    print("Telegram kurulumu başlatılıyor.")
    token = input("TELEGRAM_BOT_TOKEN: ").strip()
    if not token:
        print("Token gerekli. Kurulum iptal edildi.")
        return 1

    public_base = input(
        "Webhook public base URL (ör: https://nasri.example.com) [opsiyonel]: "
    ).strip()
    secret = secrets.token_urlsafe(24)

    env_file = _ensure_env_file()
    lines = _load_env_lines(env_file)
    lines = _upsert(lines, "TELEGRAM_ENABLED", "1")
    lines = _upsert(lines, "TELEGRAM_BOT_TOKEN", token)
    lines = _upsert(lines, "TELEGRAM_WEBHOOK_SECRET", secret)
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f".env güncellendi: {env_file}")

    if public_base:
        webhook = public_base.rstrip("/") + "/messaging/telegram/webhook"
        ok, detail = _set_telegram_webhook(token, webhook, secret)
        if ok:
            print("Telegram webhook ayarlandı.")
        else:
            print(f"Webhook ayarlanamadı: {detail}")
            print("Elle setWebhook çağrısı yapmanız gerekebilir.")
    else:
        print("Webhook URL verilmedi. Sadece .env güncellendi.")
    return 0
