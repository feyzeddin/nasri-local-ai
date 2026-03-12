"""
model_manager.py — Otomatik model araştırma ve adaptif güncelleme döngüsü.

Adaptif kontrol aralığı (güncelleme bulunamazsa aralık uzar):
  Güncelleme bulundu  →  1 gün sonra kontrol
  Yok (1. seferinde) →  4 gün
  Yok (2. seferinde) →  7 gün
  Yok (3+. seferinde) → 14 gün (maksimum, döngü devam eder)
  Güncelleme bulununca → 1 güne sıfırla

Döngü:
1. Kullanıcının dilini ve mevcut modeli değerlendirir
2. OLLAMA_MODELS listesinden daha iyi bir model arar
3. Uygun model varsa arka planda indirir, .env günceller, servisi yeniden başlatır
4. Araştırma sonucunu kaydeder, bir sonraki kontrol aralığını ayarlar
"""
from __future__ import annotations

import datetime as dt
import json
import os
import secrets
import subprocess
from pathlib import Path
from typing import Optional

from .config import data_dir, install_dir
from .notifications import push as _notify

# ------------------------------------------------------------------ #
# Model veritabanı (Ollama üzerinden erişilebilir)
# Skor: 1-10, yüksek = daha iyi
# ------------------------------------------------------------------ #

OLLAMA_MODELS: list[dict] = [
    {
        "name": "qwen3:4b",
        "size_gb": 2.5,
        "languages": ["tr", "en", "zh", "ar", "de", "fr", "es", "pt", "it", "ru", "ja", "ko",
                      "nl", "pl", "sv", "da", "fi", "no", "cs", "hu", "ro"],
        "score_multilingual": 9,
        "score_turkish": 9,
        "min_ram_gb": 3,
        "notes": "Qwen3 4B — 119 dil, hızlı, düşük RAM, Türkçe mükemmel",
        "added_version": "0.3.24",
    },
    {
        "name": "aya-expanse:8b",
        "size_gb": 5.1,
        "languages": ["tr", "ar", "hi", "zh", "fr", "de", "en", "es", "pt", "it", "nl",
                      "ru", "ja", "ko", "pl", "sv", "uk", "vi", "id", "el", "he"],
        "score_multilingual": 10,
        "score_turkish": 10,
        "min_ram_gb": 7,
        "notes": "Cohere Aya Expanse 8B — 23 dil için özel eğitildi, Türkçe en iyi",
        "added_version": "0.3.24",
    },
    {
        "name": "gemma3:4b",
        "size_gb": 3.3,
        "languages": ["tr", "en", "de", "fr", "es", "pt", "it", "ar", "zh", "ja", "ko",
                      "ru", "hi", "nl", "pl", "sv"],
        "score_multilingual": 8,
        "score_turkish": 8,
        "min_ram_gb": 4,
        "notes": "Gemma 3 4B — Google, 140+ dil, hızlı, 128K context",
        "added_version": "0.3.24",
    },
    {
        "name": "qwen2.5:7b",
        "size_gb": 4.7,
        "languages": ["zh", "en", "tr", "ar", "de", "fr", "es", "pt", "it", "ru", "ja", "ko"],
        "score_multilingual": 9,
        "score_turkish": 8,
        "min_ram_gb": 6,
        "notes": "Qwen 2.5 7B — Alibaba, mükemmel çok dilli performans",
        "added_version": "0.3.22",
    },
    {
        "name": "llama3.2:3b",
        "size_gb": 2.0,
        "languages": ["en", "tr", "de", "fr", "es", "pt", "it"],
        "score_multilingual": 7,
        "score_turkish": 7,
        "min_ram_gb": 4,
        "notes": "Llama 3.2 3B — küçük ve hızlı, düşük RAM'li cihazlar için",
        "added_version": "0.3.22",
    },
    {
        "name": "llama3.1:8b",
        "size_gb": 4.7,
        "languages": ["en", "tr", "de", "fr", "es", "pt", "it", "hi"],
        "score_multilingual": 8,
        "score_turkish": 7,
        "min_ram_gb": 6,
        "notes": "Llama 3.1 8B — Meta, dengeli performans",
        "added_version": "0.3.22",
    },
    {
        "name": "llama3:8b",
        "size_gb": 4.7,
        "languages": ["en", "tr", "de", "fr", "es", "pt"],
        "score_multilingual": 7,
        "score_turkish": 6,
        "min_ram_gb": 6,
        "notes": "Llama 3 8B — temel seviye varsayılan",
        "added_version": "0.3.22",
    },
]

_UPGRADE_SCORE_THRESHOLD = 1  # mevcut modelden en az bu kadar daha iyi olmalı

# ------------------------------------------------------------------ #
# Adaptif kontrol aralığı
# ------------------------------------------------------------------ #

# Güncelleme bulunamadığında ardışık başarısız kontrol sayısına göre gün cinsinden aralıklar
_RESEARCH_INTERVAL_LADDER: list[int] = [1, 4, 7, 14]


def _research_state_file() -> Path:
    return data_dir() / "model_research_state.json"


def _load_research_state() -> dict:
    f = _research_state_file()
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_research_state(state: dict) -> None:
    f = _research_state_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def should_research_models(last_checked_iso: Optional[str] = None, interval_hours: int = 24) -> bool:
    """Adaptif aralıkla araştırma zamanı geldi mi?"""
    state = _load_research_state()
    last_checked = state.get("last_checked")
    if not last_checked:
        return True
    interval_days = state.get("current_interval_days", 1)
    try:
        last = dt.datetime.fromisoformat(last_checked)
        elapsed = dt.datetime.now(dt.timezone.utc) - last
        return elapsed >= dt.timedelta(days=interval_days)
    except Exception:
        return True


def record_research_result(found_upgrade: bool) -> None:
    """
    Araştırma sonucunu kaydeder ve adaptif aralığı günceller.

    Güncelleme bulundu → aralık 1 güne sıfırlanır
    Bulunamadı        → aralık merdivende bir basamak yukarı çıkar (max 14 gün)
    """
    state = _load_research_state()
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    if found_upgrade:
        state["consecutive_no_update"] = 0
        state["current_interval_days"] = _RESEARCH_INTERVAL_LADDER[0]  # 1 gün
    else:
        no_update = state.get("consecutive_no_update", 0) + 1
        state["consecutive_no_update"] = no_update
        idx = min(no_update, len(_RESEARCH_INTERVAL_LADDER) - 1)
        state["current_interval_days"] = _RESEARCH_INTERVAL_LADDER[idx]

    state["last_checked"] = now_iso
    _save_research_state(state)


def get_next_check_info() -> str:
    """Bir sonraki kontrol zamanını okunabilir string olarak döner."""
    state = _load_research_state()
    last = state.get("last_checked")
    interval_days = state.get("current_interval_days", 1)
    if not last:
        return "henüz kontrol edilmedi"
    try:
        next_check = dt.datetime.fromisoformat(last) + dt.timedelta(days=interval_days)
        return next_check.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "bilinmiyor"


# ------------------------------------------------------------------ #
# İhtiyaç listesi (needs store)
# ------------------------------------------------------------------ #

def _needs_file() -> Path:
    return data_dir() / "model_needs.json"


def _load_needs() -> list[dict]:
    f = _needs_file()
    if not f.exists():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_needs(items: list[dict]) -> None:
    f = _needs_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def add_need(description: str, kind: str = "language_quality", trigger: str = "auto") -> str:
    """İhtiyaç listesine yeni bir madde ekler. Oluşturulan ID'yi döner."""
    needs = _load_needs()
    for n in needs:
        if not n.get("resolved") and n.get("kind") == kind:
            return n["id"]
    need_id = secrets.token_hex(6)
    needs.insert(0, {
        "id": need_id,
        "kind": kind,
        "description": description,
        "trigger": trigger,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "resolved": False,
        "resolved_by": None,
        "resolved_at": None,
    })
    _save_needs(needs)
    return need_id


def resolve_need(kind: str, resolved_by: str) -> None:
    """Belirtilen türdeki açık ihtiyaçları çözüldü olarak işaretler."""
    needs = _load_needs()
    changed = False
    for n in needs:
        if not n.get("resolved") and n.get("kind") == kind:
            n["resolved"] = True
            n["resolved_by"] = resolved_by
            n["resolved_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
            changed = True
    if changed:
        _save_needs(needs)


def get_open_needs() -> list[dict]:
    return [n for n in _load_needs() if not n.get("resolved")]


# ------------------------------------------------------------------ #
# Sistem bilgisi
# ------------------------------------------------------------------ #

def _available_ram_gb() -> float:
    """Kullanılabilir RAM'i GB cinsinden döner."""
    try:
        import platform
        if platform.system() == "Linux":
            with open("/proc/meminfo", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        kb = int(line.split()[1])
                        return kb / 1024 / 1024
        elif platform.system() == "Darwin":
            import subprocess as _sp
            r = _sp.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True)
            if r.returncode == 0:
                return int(r.stdout.strip()) / 1024 / 1024 / 1024
        elif platform.system() == "Windows":
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong),
                             ("dwMemoryLoad", ctypes.c_ulong),
                             ("ullTotalPhys", ctypes.c_ulonglong),
                             ("ullAvailPhys", ctypes.c_ulonglong),
                             ("ullTotalPageFile", ctypes.c_ulonglong),
                             ("ullAvailPageFile", ctypes.c_ulonglong),
                             ("ullTotalVirtual", ctypes.c_ulonglong),
                             ("ullAvailVirtual", ctypes.c_ulonglong),
                             ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))  # type: ignore[attr-defined]
            return stat.ullAvailPhys / 1024 / 1024 / 1024
    except Exception:
        pass
    return 8.0


def _detect_user_language() -> str:
    """
    Kullanıcının dilini state, location önbelleği veya env'den okur.
    Dil kodu döner (örn. 'tr', 'en', 'de').
    """
    # 1. state.json'dan
    try:
        state_path = data_dir() / "state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            lang = state.get("detected_language")
            if lang:
                return lang.lower()
    except Exception:
        pass
    # 2. Konum önbelleğinden ülkeye göre tahmin
    try:
        from .location import _load_cached as _loc_cache
        cached = _loc_cache()
        country_code = cached.get("country_code", "").upper()
        _COUNTRY_LANG = {
            "TR": "tr", "AZ": "tr", "US": "en", "GB": "en", "AU": "en",
            "DE": "de", "AT": "de", "CH": "de", "FR": "fr", "BE": "fr",
            "ES": "es", "MX": "es", "AR": "es", "BR": "pt", "PT": "pt",
            "RU": "ru", "UA": "uk", "CN": "zh", "TW": "zh", "JP": "ja",
            "KR": "ko", "SA": "ar", "AE": "ar", "EG": "ar", "IN": "hi",
            "NL": "nl", "PL": "pl", "SE": "sv", "DK": "da", "NO": "no",
            "FI": "fi", "IT": "it", "RO": "ro", "HU": "hu", "CZ": "cs",
        }
        if country_code in _COUNTRY_LANG:
            return _COUNTRY_LANG[country_code]
    except Exception:
        pass
    # 3. DEFAULT_LOCALE env
    return os.getenv("DEFAULT_LOCALE", "tr").lower()


def _get_current_model() -> str:
    """Mevcut MODEL_NAME'i .env'den okur."""
    env_path = install_dir() / "project" / "nasri-core" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("MODEL_NAME="):
                val = line.split("=", 1)[1].strip()
                if val:
                    return val
    return os.getenv("MODEL_NAME", "llama3")


def _model_score(model_info: dict, lang: str) -> int:
    """Kullanıcı diline göre modelin skorunu döner."""
    if lang == "tr":
        return model_info.get("score_turkish", 5)
    # Dilin model'in desteklenen dilleri arasında olup olmadığını kontrol et
    langs = model_info.get("languages", [])
    if lang in langs:
        return model_info.get("score_multilingual", 5)
    # Dil desteklenmiyorsa skoru düşür
    return max(1, model_info.get("score_multilingual", 5) - 3)


def _find_model_info(model_name: str) -> Optional[dict]:
    base = model_name.split(":")[0] if ":" in model_name else model_name
    for m in OLLAMA_MODELS:
        if m["name"] == model_name or m["name"].split(":")[0] == base:
            return m
    return None


# ------------------------------------------------------------------ #
# Ollama API
# ------------------------------------------------------------------ #

def _ollama_local_models(ollama_url: str) -> list[str]:
    """Ollama'da yüklü modellerin listesini döner."""
    try:
        import urllib.request
        with urllib.request.urlopen(f"{ollama_url}/api/tags", timeout=5) as r:
            data = json.loads(r.read().decode())
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def _ollama_pull(model_name: str) -> bool:
    """Modeli Ollama ile indirir. Zaman aşımı yok — model boyutu ne olursa olsun bekler."""
    try:
        result = subprocess.run(
            ["ollama", "pull", model_name],
            # timeout yok: büyük modeller uzun sürebilir
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except Exception:
        return False


# ------------------------------------------------------------------ #
# .env güncelleme ve servis yeniden başlatma
# ------------------------------------------------------------------ #

def _update_env_model(model_name: str) -> bool:
    env_path = install_dir() / "project" / "nasri-core" / ".env"
    if not env_path.exists():
        return False
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
        replaced = False
        out = []
        for line in lines:
            if line.strip().startswith("MODEL_NAME="):
                out.append(f"MODEL_NAME={model_name}")
                replaced = True
            else:
                out.append(line)
        if not replaced:
            out.append(f"MODEL_NAME={model_name}")
        env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
        return True
    except Exception:
        return False


def _request_service_restart() -> None:
    try:
        (data_dir() / ".restart_flag").touch()
    except Exception:
        pass


# ------------------------------------------------------------------ #
# Ana araştırma döngüsü
# ------------------------------------------------------------------ #

def run_model_research_cycle(ollama_url: str = "http://localhost:11434") -> None:
    """
    Adaptif model araştırma döngüsü.
    Daha iyi model bulunursa indirir ve geçiş yapar.
    Sonuç ne olursa olsun record_research_result() çağrılır.
    """
    lang = _detect_user_language()
    ram_gb = _available_ram_gb()
    current_model = _get_current_model()
    current_info = _find_model_info(current_model)
    current_score = _model_score(current_info, lang) if current_info else 5

    # Mevcut modelin dil skoru düşükse ihtiyaç listesine ekle
    open_needs = get_open_needs()
    needs_better_lang = any(n.get("kind") == "language_quality" for n in open_needs)
    if current_score < 7 or needs_better_lang:
        add_need(
            description=(
                f"Kullanıcı dili: '{lang}'. "
                f"Mevcut model '{current_model}' skoru: {current_score}/10. "
                "Daha iyi çok dilli model öneriliyor."
            ),
            kind="language_quality",
            trigger="auto_research",
        )

    # En uygun alternatifi bul
    best: Optional[dict] = None
    best_score = current_score
    local_models = _ollama_local_models(ollama_url)

    for m in OLLAMA_MODELS:
        if m["name"] == current_model:
            continue
        if m.get("min_ram_gb", 0) > ram_gb:
            continue
        score = _model_score(m, lang)
        if score > best_score + _UPGRADE_SCORE_THRESHOLD - 1:
            best_score = score
            best = m

    if not best:
        record_research_result(found_upgrade=False)
        return

    model_name = best["name"]
    already_local = any(
        model_name in lm or model_name.split(":")[0] in lm
        for lm in local_models
    )

    if already_local:
        _apply_model_switch(model_name, lang, current_model, best)
        record_research_result(found_upgrade=True)
        return

    _notify(
        title=f"Model indiriliyor: {model_name}",
        message=(
            f"'{lang}' dili için daha iyi model bulundu.\n"
            f"{best.get('notes', '')}\n"
            f"Arka planda indiriliyor ({best.get('size_gb', '?')} GB)..."
        ),
        kind="info",
    )

    success = _ollama_pull(model_name)
    if success:
        _apply_model_switch(model_name, lang, current_model, best)
        record_research_result(found_upgrade=True)
    else:
        _notify(
            title=f"Model indirilemedi: {model_name}",
            message="İndirme sırasında hata oluştu. Adaptif zamanlayıcı ile tekrar denenecek.",
            kind="error",
        )
        record_research_result(found_upgrade=False)


def _apply_model_switch(
    new_model: str, lang: str, old_model: str, model_info: dict
) -> None:
    """Modeli değiştirir, ihtiyacı çözer, bildirim gönderir."""
    if not _update_env_model(new_model):
        return

    resolve_need("language_quality", resolved_by=new_model)

    _notify(
        title=f"Model güncellendi: {new_model}",
        message=(
            f"{old_model} → {new_model}\n"
            f"{model_info.get('notes', '')}\n"
            "Servis yeniden başlatılıyor..."
        ),
        kind="update",
    )
    _request_service_restart()
