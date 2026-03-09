"""
healer.py — Nasri çalışma zamanı otomatik onarım motoru.

preflight veya servis döngüsü tarafından tespit edilen sorunları
önce kural tabanlı, ardından AI destekli (Ollama) yöntemlerle çözmeye çalışır.
"""
from __future__ import annotations

import importlib
import subprocess
import sys
import time
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .preflight import CheckResult


# ---------------------------------------------------------------------------
# Kural tabanlı onarım
# ---------------------------------------------------------------------------


def _heal_missing_module(detail: str) -> bool:
    """'No module named X' hatasında pip install dener."""
    import re  # noqa: PLC0415

    m = re.search(r"No module named '([^']+)'", detail)
    if not m:
        return False
    mod = m.group(1).replace(".", "-")
    print(f"  [heal] pip install {mod} deneniyor...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", mod, "--quiet"],
            timeout=60,
        )
        if result.returncode == 0:
            # modülü yeniden yükle
            try:
                importlib.import_module(m.group(1))
            except ImportError:
                pass
            return True
    except Exception:
        pass
    return False


def _heal_redis(detail: str) -> bool:
    """Redis ping başarısızsa servisi başlatmayı dener."""
    if "Connection" not in detail and "refused" not in detail and "ping" not in detail.lower():
        return False
    print("  [heal] Redis başlatılmaya çalışılıyor...")
    # systemctl ile dene
    r = subprocess.run(
        ["systemctl", "start", "redis-server"],
        capture_output=True,
        timeout=10,
    )
    if r.returncode == 0:
        time.sleep(2)
        return True
    # daemonize ile dene
    subprocess.Popen(
        ["redis-server", "--daemonize", "yes", "--logfile", "/tmp/redis-nasri.log"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(2)
    return True


def _heal_port_conflict(name: str) -> bool:
    """Port kullanımdaysa onu serbest bırakmaya çalışır (fuser)."""
    import re  # noqa: PLC0415

    m = re.search(r"port (\d+)", name)
    if not m:
        return False
    port = m.group(1)
    print(f"  [heal] Port {port} serbest bırakılmaya çalışılıyor (fuser -k)...")
    subprocess.run(
        ["fuser", "-k", f"{port}/tcp"],
        capture_output=True,
        timeout=10,
    )
    time.sleep(1)
    return True


def rule_based_heal(result: "CheckResult") -> bool:
    """
    Tek bir CheckResult için kural tabanlı onarım uygular.
    Başarılıysa True döner.
    """
    if result.ok:
        return True  # zaten sağlıklı

    name_lower = result.name.lower()
    detail = result.detail

    if "module:" in name_lower:
        return _heal_missing_module(detail)

    if "redis" in name_lower:
        return _heal_redis(detail)

    if "port" in name_lower and "boş" in name_lower:
        return _heal_port_conflict(result.name)

    return False


# ---------------------------------------------------------------------------
# AI destekli onarım (Ollama)
# ---------------------------------------------------------------------------


def _ollama_available() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3):  # noqa: S310
            return True
    except Exception:
        return False


def _ask_ollama(prompt: str, model: str = "llama3") -> str:
    import json  # noqa: PLC0415

    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(  # noqa: S310
        "http://localhost:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            data = json.loads(resp.read())
            return data.get("response", "")
    except Exception as exc:
        return f"[hata: {exc}]"


def _safe_commands(response: str) -> list[str]:
    """
    Ollama yanıtından güvenli bash komutlarını çıkarır.
    Yalnızca izin verilenler çalıştırılır.
    """
    ALLOWED_PREFIXES = ("pip ", "pip3 ", "python ", "python3 ", "systemctl ", "redis-server ")
    cmds: list[str] = []
    for line in response.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Kod bloğu işaretlerini temizle
        if line.startswith("```"):
            continue
        if any(line.startswith(p) for p in ALLOWED_PREFIXES):
            cmds.append(line)
    return cmds


def ai_heal(result: "CheckResult", model: str = "llama3") -> bool:
    """
    Ollama LLM'den onarım önerisi alır ve güvenli komutları çalıştırır.
    """
    if not _ollama_available():
        print("  [heal/ai] Ollama erişilemiyor, AI tanı atlanıyor")
        return False

    prompt = (
        "Sen bir Linux sistem yöneticisi ve Python uzmanısın. "
        "Aşağıdaki servis başlatma hatasını düzeltmek için SADECE "
        "çalıştırılabilir bash komutları ver. "
        "Her komut ayrı satırda olsun. Açıklama ekleme.\n\n"
        f"KONTROL ADI: {result.name}\n"
        f"HATA DETAYI: {result.detail}\n\n"
        "ÖNEMLI: Sadece pip install, systemctl start/enable, "
        "redis-server veya python3 komutları öner. "
        "rm -rf gibi tehlikeli komutlar önerme."
    )

    print(f"  [heal/ai] Ollama'ya tanı isteği gönderiliyor: {result.name}")
    response = _ask_ollama(prompt, model=model)

    if not response or response.startswith("[hata"):
        print(f"  [heal/ai] Yanıt alınamadı: {response}")
        return False

    cmds = _safe_commands(response)
    if not cmds:
        print("  [heal/ai] Güvenli komut bulunamadı")
        return False

    success = False
    for cmd in cmds:
        print(f"  [heal/ai] Çalıştırılıyor: {cmd}")
        try:
            r = subprocess.run(cmd.split(), capture_output=True, text=True, timeout=60)
            if r.returncode == 0:
                print(f"  [heal/ai] Başarılı: {cmd}")
                success = True
            else:
                print(f"  [heal/ai] Başarısız ({r.returncode}): {r.stderr.strip()[:120]}")
        except Exception as exc:
            print(f"  [heal/ai] Hata: {exc}")

    return success


# ---------------------------------------------------------------------------
# Toplu onarım: preflight sonuçlarına göre çalışır
# ---------------------------------------------------------------------------


def heal_results(results: list["CheckResult"], model: str = "llama3") -> dict[str, bool]:
    """
    Başarısız her kontrol için önce kural tabanlı, sonra AI onarımı uygular.

    Dönüş: {kontrol_adı: onarım_başarılı}
    """
    healed: dict[str, bool] = {}
    for r in results:
        if r.ok:
            continue
        print(f"\n[healer] Onarım başlatılıyor: {r.name}")
        fixed = rule_based_heal(r)
        if not fixed:
            fixed = ai_heal(r, model=model)
        healed[r.name] = fixed
        status = "onarıldı" if fixed else "onarılamadı"
        print(f"[healer] {r.name}: {status}")
    return healed
