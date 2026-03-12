"""
selfheal_log.py — Log tabanlı çökme analizi ve otomatik onarım

Akış:
  1. collect_recent_logs()  — journalctl / log dosyasından son N satır
  2. extract_errors()       — bilinen hata kalıpları (regex)
  3. diagnose_locally()     — bilinen hatalar → doğrudan düzeltme komutu
  4. diagnose_with_ai()     — bilinmeyen hatalar → Groq/Ollama AI tanısı
  5. execute_fix()          — güvenli beyaz liste ile komutu çalıştır
  6. run_crash_recovery()   — tüm akışı çalıştıran ana fonksiyon

Güvenlik:
  - AI yanıtından yalnızca beyaz listedeki komutlar çalıştırılır
  - Maksimum 5 komut çalıştırılır (sonsuz döngü önlemi)
  - Her çalıştırma loglanır
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any


# ------------------------------------------------------------------ #
# Log toplama
# ------------------------------------------------------------------ #

def collect_recent_logs(lines: int = 80) -> str:
    """
    Son N satır servis logunu döner.
    Önce journalctl'i dener, sonra log dosyasına bakar.
    """
    # 1. journalctl
    try:
        r = subprocess.run(
            ["journalctl", "-u", "nasri.service", "-n", str(lines),
             "--no-pager", "--output=short"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout
    except Exception:
        pass

    # 2. Log dosyası
    try:
        from .config import data_dir
        log_file = data_dir() / "nasri.log"
        if log_file.exists():
            text = log_file.read_text(encoding="utf-8", errors="replace")
            return "\n".join(text.splitlines()[-lines:])
    except Exception:
        pass

    return ""


# ------------------------------------------------------------------ #
# Hata kalıpları
# ------------------------------------------------------------------ #

# (regex, hata_tipi, gruba_göre_mesaj)
_ERROR_PATTERNS: list[tuple[str, str]] = [
    (r"No module named '([^']+)'",          "missing_module"),
    (r"ModuleNotFoundError: No module named '([^']+)'", "missing_module"),
    (r"ImportError: ([^\n]+)",              "import_error"),
    (r"ConnectionRefusedError",             "connection_refused"),
    (r"Address already in use",             "port_conflict"),
    (r"FileNotFoundError: ([^\n]+)",        "file_not_found"),
    (r"PermissionError: ([^\n]+)",          "permission_error"),
    (r"Traceback \(most recent call last\)", "traceback"),
    (r"SystemExit: (\d+)",                  "exit_code"),
    (r"redis\.exceptions\.",               "redis_error"),
    (r"httpx\.ConnectError",               "connect_error"),
    (r"pip install",                       "pip_hint"),
]

# Modül adı → pip paket adı (healer.py ile senkronize)
_MODULE_TO_PACKAGE: dict[str, str] = {
    "textual": "textual>=0.60.0",
    "paho": "paho-mqtt>=2.0.0",
    "bs4": "beautifulsoup4",
    "PIL": "Pillow",
    "yaml": "PyYAML",
    "dotenv": "python-dotenv",
    "psutil": "psutil>=5.9.0",
    "zeroconf": "zeroconf>=0.136.0",
    "paramiko": "paramiko>=3.0.0",
    "chromadb": "chromadb",
    "cryptography": "cryptography",
    "httpx": "httpx>=0.28.0",
    "fastapi": "fastapi>=0.100.0",
    "uvicorn": "uvicorn[standard]",
    "redis": "redis>=4.0.0",
}


def extract_errors(log_text: str) -> list[dict[str, str]]:
    """Log metninden bilinen hata kalıplarını çıkarır."""
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for pattern, error_type in _ERROR_PATTERNS:
        for m in re.finditer(pattern, log_text):
            detail = m.group(1) if m.lastindex else m.group(0)
            key = f"{error_type}:{detail}"
            if key not in seen:
                seen.add(key)
                found.append({"type": error_type, "detail": detail, "raw": m.group(0)})
    return found


# ------------------------------------------------------------------ #
# Yerel tanı (bilinen kalıplar)
# ------------------------------------------------------------------ #

def diagnose_locally(errors: list[dict[str, str]]) -> list[dict[str, Any]]:
    """
    Bilinen hata kalıpları için doğrudan düzeltme komutları üretir.
    Dönüş: [{"description": str, "command": list[str]}]
    """
    fixes: list[dict[str, Any]] = []
    for err in errors:
        t = err["type"]
        detail = err["detail"]

        if t == "missing_module":
            mod = detail.split(".")[0]
            pkg = _MODULE_TO_PACKAGE.get(mod, mod.replace("_", "-"))
            fixes.append({
                "description": f"Eksik paket: {pkg}",
                "command": [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
            })

        elif t == "redis_error" or (t == "connection_refused" and "6379" in err.get("raw", "")):
            fixes.append({
                "description": "Redis servisi başlatılıyor",
                "command": ["systemctl", "start", "redis-server"],
            })

        elif t == "port_conflict":
            m = re.search(r"(\d{4,5})", err.get("raw", ""))
            if m:
                fixes.append({
                    "description": f"Port {m.group(1)} serbest bırakılıyor",
                    "command": ["fuser", "-k", f"{m.group(1)}/tcp"],
                })

    # Tekrar eden komutları kaldır
    seen_cmds: set[str] = set()
    unique: list[dict[str, Any]] = []
    for fix in fixes:
        key = " ".join(fix["command"])
        if key not in seen_cmds:
            seen_cmds.add(key)
            unique.append(fix)
    return unique


# ------------------------------------------------------------------ #
# AI tanısı (Groq → Ollama)
# ------------------------------------------------------------------ #

_AI_PROMPT_TEMPLATE = """\
Sen bir Linux sistem yöneticisi ve Python uzmanısın.
Aşağıdaki servis log çıktısını analiz et ve düzeltme öner.

SADECE JSON ile yanıt ver, başka hiçbir şey yazma:
{{
  "diagnosis": "kısa açıklama",
  "fixes": [
    {{"description": "ne yapıyor", "pip_package": "paket adı veya boş string"}},
    {{"description": "ne yapıyor", "system_command": "komut veya boş string"}}
  ]
}}

LOG:
{log_excerpt}
"""

_GROQ_ALLOWED_COMMANDS = frozenset([
    "pip", "pip3", "python", "python3",
    "systemctl", "redis-server", "apt-get", "apt",
    "fuser", "pkill",
])


def _ask_ai(log_excerpt: str) -> str:
    """Groq veya Ollama'ya log gönderir, JSON yanıt bekler."""
    prompt = _AI_PROMPT_TEMPLATE.format(log_excerpt=log_excerpt[-2000:])

    # 1. Groq dene
    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key:
        try:
            groq_url = os.getenv(
                "GROQ_API_URL",
                "https://api.groq.com/openai/v1/chat/completions",
            )
            groq_model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
            payload = json.dumps({
                "model": groq_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 400,
                "temperature": 0.1,
            }).encode()
            req = urllib.request.Request(  # noqa: S310
                groq_url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {groq_key}",
                },
            )
            with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
                data = json.loads(resp.read())
                return data["choices"][0]["message"]["content"]
        except Exception as exc:
            print(f"  [selfheal/ai] Groq hatası: {exc}")

    # 2. Ollama dene
    try:
        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        model = os.getenv("MODEL_NAME", "llama3")
        payload = json.dumps({
            "model": model,
            "prompt": prompt,
            "stream": False,
        }).encode()
        req = urllib.request.Request(  # noqa: S310
            f"{ollama_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            data = json.loads(resp.read())
            return data.get("response", "")
    except Exception as exc:
        print(f"  [selfheal/ai] Ollama hatası: {exc}")

    return ""


def diagnose_with_ai(log_text: str) -> list[dict[str, Any]]:
    """
    AI'ya log gönderir, JSON yanıttan güvenli düzeltme komutları çıkarır.
    """
    print("  [selfheal/ai] AI tanısı başlatılıyor...")
    raw = _ask_ai(log_text)
    if not raw:
        return []

    # JSON bloğunu çıkar
    try:
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if not m:
            return []
        data = json.loads(m.group(0))
    except Exception:
        return []

    diagnosis = data.get("diagnosis", "")
    if diagnosis:
        print(f"  [selfheal/ai] Tanı: {diagnosis}")

    fixes: list[dict[str, Any]] = []
    for fix in data.get("fixes", []):
        desc = fix.get("description", "")

        # pip paketi
        pkg = (fix.get("pip_package") or "").strip()
        if pkg and pkg not in ("", "boş string"):
            fixes.append({
                "description": desc or f"pip install {pkg}",
                "command": [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
            })

        # sistem komutu (güvenlik filtresi)
        sys_cmd = (fix.get("system_command") or "").strip()
        if sys_cmd and sys_cmd not in ("", "boş string"):
            parts = sys_cmd.split()
            if parts and parts[0] in _GROQ_ALLOWED_COMMANDS:
                fixes.append({
                    "description": desc or sys_cmd,
                    "command": parts,
                })

    return fixes


# ------------------------------------------------------------------ #
# Komutu çalıştır
# ------------------------------------------------------------------ #

def execute_fix(fix: dict[str, Any], verbose: bool = True) -> bool:
    """Tek bir düzeltme komutunu çalıştırır. Başarılıysa True döner."""
    cmd = fix["command"]
    desc = fix.get("description", " ".join(cmd))

    # Son güvenlik filtresi
    if not cmd or cmd[0] not in (
        sys.executable, "pip", "pip3", "python", "python3",
        "systemctl", "redis-server", "apt-get", "apt", "fuser", "pkill",
    ):
        if verbose:
            print(f"  [selfheal] Güvenlik: izin verilmeyen komut atlandı: {cmd[0]}")
        return False

    if verbose:
        print(f"  [selfheal] Uygulama: {desc}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            if verbose:
                print(f"  [selfheal] Başarılı: {' '.join(cmd)}")
            return True
        else:
            if verbose:
                print(f"  [selfheal] Başarısız (rc={r.returncode}): {r.stderr.strip()[:100]}")
    except Exception as exc:
        if verbose:
            print(f"  [selfheal] Hata: {exc}")
    return False


# ------------------------------------------------------------------ #
# Ana fonksiyon
# ------------------------------------------------------------------ #

def run_crash_recovery(verbose: bool = True) -> bool:
    """
    Servis çökmesi sonrası otomatik kurtarma döngüsü:
    1. Son logları toplar
    2. Yerel tanı → bilinen hatalar → otomatik düzelt
    3. Bilinmeyen → AI tanısı → güvenli komutları uygula
    4. Sonucu raporlar

    Dönüş: en az bir düzeltme başarılıysa True
    """
    def log(msg: str) -> None:
        if verbose:
            print(f"[selfheal] {msg}")

    log("Çökme kurtarma başlatılıyor...")

    log_text = collect_recent_logs()
    if not log_text:
        log("Log bulunamadı.")
        return False

    errors = extract_errors(log_text)
    if not errors:
        log("Bilinen hata kalıbı bulunamadı.")
        return False

    log(f"{len(errors)} hata kalıbı tespit edildi:")
    for e in errors:
        log(f"  [{e['type']}] {e['detail'][:80]}")

    # Yerel tanı
    fixes = diagnose_locally(errors)

    # Yerel tanı yetersizse AI'ya sor
    if not fixes:
        log("Yerel tanı yetersiz, AI tanısı deneniyor...")
        fixes = diagnose_with_ai(log_text)

    if not fixes:
        log("Düzeltme bulunamadı.")
        return False

    log(f"{len(fixes)} düzeltme uygulanacak (maks 5):")
    applied = 0
    for fix in fixes[:5]:
        if execute_fix(fix, verbose=verbose):
            applied += 1

    log(f"Sonuç: {applied}/{min(len(fixes), 5)} düzeltme uygulandı.")

    # Bildirim gönder
    try:
        from .notifications import push as _notify
        _notify(
            title="Otomatik onarım" + (" başarılı" if applied else " başarısız"),
            message=f"{applied}/{min(len(fixes), 5)} düzeltme uygulandı.",
            kind="info" if applied else "warning",
        )
    except Exception:
        pass

    return applied > 0
