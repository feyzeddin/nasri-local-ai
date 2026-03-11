"""
model_manager.py — Otomatik model araştırma, ihtiyaç listesi ve güncelleme.

Günlük döngü:
1. Kullanıcının dilini ve mevcut modelin kalitesini değerlendirir
2. Daha uygun model varsa Ollama üzerinden arka planda indirir
3. İndirme tamamlandığında .env günceller, servisi yeniden başlatır
4. Çözülemeyen gereksinimleri ihtiyaç listesinde saklar
5. Bir gereksinim çözüldüğünde listeden çıkarır, bildirim gönderir
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
# Önerilen model veritabanı (Ollama üzerinden erişilebilir)
# ------------------------------------------------------------------ #

OLLAMA_MODELS: list[dict] = [
    {
        "name": "aya-expanse:8b",
        "size_gb": 4.7,
        "languages": ["tr", "ar", "hi", "zh", "fr", "de", "en", "es", "pt", "it", "nl", "ru", "ja", "ko"],
        "score_multilingual": 9,
        "score_turkish": 9,
        "min_ram_gb": 6,
        "notes": "Cohere Aya Expanse — 23 dil, Türkçe için en iyi seçim",
    },
    {
        "name": "qwen2.5:7b",
        "size_gb": 4.7,
        "languages": ["zh", "en", "tr", "ar", "de", "fr", "es", "pt", "it", "ru", "ja", "ko"],
        "score_multilingual": 9,
        "score_turkish": 8,
        "min_ram_gb": 6,
        "notes": "Qwen 2.5 7B — Alibaba, mükemmel çok dilli performans",
    },
    {
        "name": "llama3.1:8b",
        "size_gb": 4.7,
        "languages": ["en", "tr", "de", "fr", "es", "pt", "it", "hi"],
        "score_multilingual": 8,
        "score_turkish": 7,
        "min_ram_gb": 6,
        "notes": "Llama 3.1 8B — dengeli performans",
    },
    {
        "name": "llama3.2:3b",
        "size_gb": 2.0,
        "languages": ["en", "tr", "de", "fr", "es", "pt", "it"],
        "score_multilingual": 7,
        "score_turkish": 7,
        "min_ram_gb": 4,
        "notes": "Llama 3.2 3B — küçük ve hızlı, düşük RAM'li cihazlar için",
    },
    {
        "name": "gemma2:9b",
        "size_gb": 5.5,
        "languages": ["en", "tr", "de", "fr", "es", "pt", "it", "ar"],
        "score_multilingual": 8,
        "score_turkish": 7,
        "min_ram_gb": 8,
        "notes": "Gemma 2 9B — Google, yüksek kalite",
    },
    {
        "name": "mistral:7b",
        "size_gb": 4.1,
        "languages": ["en", "fr", "de", "es", "it", "tr"],
        "score_multilingual": 7,
        "score_turkish": 6,
        "min_ram_gb": 6,
        "notes": "Mistral 7B v0.3",
    },
    {
        "name": "llama3:8b",
        "size_gb": 4.7,
        "languages": ["en", "tr", "de", "fr", "es", "pt"],
        "score_multilingual": 7,
        "score_turkish": 6,
        "min_ram_gb": 6,
        "notes": "Llama 3 8B — varsayılan, temel seviye",
    },
]

_UPGRADE_SCORE_THRESHOLD = 2  # mevcut modelden en az bu kadar daha iyi olmalı


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
    # Aynı türde açık ihtiyaç varsa tekrar ekleme
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
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    return kb / 1024 / 1024
    except Exception:
        pass
    return 8.0  # varsayılan: 8 GB


def _detect_user_language() -> str:
    """Kullanıcının dilini state veya env'den okur."""
    try:
        state_path = data_dir() / "state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            lang = state.get("detected_language")
            if lang:
                return lang
    except Exception:
        pass
    # DEFAULT_LOCALE env'e bak
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
    """Dil için modelin skorunu döner."""
    if lang == "tr":
        return model_info.get("score_turkish", 5)
    return model_info.get("score_multilingual", 5)


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


def _ollama_pull(model_name: str, ollama_url: str) -> bool:
    """Modeli arka planda Ollama ile indirir. Başarılıysa True döner."""
    try:
        result = subprocess.run(
            ["ollama", "pull", model_name],
            timeout=3600,  # 1 saat
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
    """Servis döngüsünün yeniden başlatma flag'ini yazar."""
    try:
        (data_dir() / ".restart_flag").touch()
    except Exception:
        pass


# ------------------------------------------------------------------ #
# Zamanlama
# ------------------------------------------------------------------ #

def should_research_models(last_checked_iso: Optional[str], interval_hours: int = 24) -> bool:
    if not last_checked_iso:
        return True
    try:
        last = dt.datetime.fromisoformat(last_checked_iso)
    except ValueError:
        return True
    return (dt.datetime.now(dt.timezone.utc) - last) >= dt.timedelta(hours=interval_hours)


# ------------------------------------------------------------------ #
# Ana döngü
# ------------------------------------------------------------------ #

def run_model_research_cycle(ollama_url: str = "http://localhost:11434") -> None:
    """
    Günlük model araştırma döngüsü.
    Servis içinden veya CLI'dan çağrılır.
    """
    lang = _detect_user_language()
    ram_gb = _available_ram_gb()
    current_model = _get_current_model()
    current_info = _find_model_info(current_model)
    current_score = _model_score(current_info, lang) if current_info else 5

    # Açık ihtiyaçları da göz önüne al
    open_needs = get_open_needs()
    needs_better_lang = any(n.get("kind") == "language_quality" for n in open_needs)

    # Mevcut modelin dil skoru düşükse ihtiyaç listesine ekle
    if current_score < 7 or needs_better_lang:
        add_need(
            description=(
                f"Kullanıcı ağırlıklı '{lang}' dilini kullanıyor. "
                f"Mevcut model '{current_model}' için skor: {current_score}/10. "
                "Daha iyi Türkçe/çok dilli model önerilir."
            ),
            kind="language_quality",
            trigger="auto_daily_check",
        )

    # En iyi alternatifi bul
    best: Optional[dict] = None
    best_score = current_score
    local_models = _ollama_local_models(ollama_url)

    for m in OLLAMA_MODELS:
        if m["name"] == current_model:
            continue
        if m.get("min_ram_gb", 0) > ram_gb:
            continue  # RAM yetersiz
        score = _model_score(m, lang)
        if score > best_score + _UPGRADE_SCORE_THRESHOLD - 1:
            best_score = score
            best = m

    if not best:
        # Daha iyi model yok
        return

    model_name = best["name"]
    already_local = any(
        model_name in lm or model_name.split(":")[0] in lm
        for lm in local_models
    )

    if already_local:
        # Model zaten yüklü — sadece geçiş yap
        _apply_model_switch(model_name, lang, current_model, best)
        return

    # Arka planda indir
    _notify(
        title=f"Model indiriliyor: {model_name}",
        message=(
            f"'{lang}' dili için daha iyi model bulundu ({best.get('notes', '')}).\n"
            f"Arka planda indiriliyor ({best.get('size_gb', '?')} GB)..."
        ),
        kind="info",
    )

    success = _ollama_pull(model_name, ollama_url)
    if success:
        _apply_model_switch(model_name, lang, current_model, best)
    else:
        _notify(
            title=f"Model indirilemedi: {model_name}",
            message="İndirme sırasında hata oluştu. Bir sonraki döngüde tekrar denecek.",
            kind="error",
        )


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
