"""
soul.py — Nasrî'nin Ruhu

Üç katmanlı kişilik mimarisi:

  KATMAN 1 — Ruh Çekirdeği (immutable)
    Etik kurallar, kimlik, yasaklanan davranışlar.
    SHA256 checksum ile mühürlüdür. Değiştirilemez.
    Kodun içine gömülü varsayılan + diskte dosya.
    Bootda doğrulanır; bozulmuşsa yerleşik varsayılana döner.

  KATMAN 2 — Kişilik (Nasri geliştirir)
    Konuşma tarzı, öğrenilen notlar, öz değerlendirme.
    Nasri etkileşimler sonrasında güncelleyebilir.
    Kullanıcı doğrudan değiştirEmez.

  KATMAN 3 — Kullanıcı Tercihleri (kullanıcı değiştirir)
    Dil, isim, yanıt uzunluğu, ilgi alanları.
    Kullanıcı komutla güncelleyebilir.

Üç katman runtime'da birleşerek sistem promptunu oluşturur.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from .config import data_dir

# ------------------------------------------------------------------ #
# Yerleşik ruh çekirdeği (kod içinde, değiştirilemez referans)
# ------------------------------------------------------------------ #

_EMBEDDED_CORE: dict[str, Any] = {
    "version": "1.0",
    "identity": {
        "name": "Nasrî",
        "type": "kişisel, tamamen yerel çalışan akıllı asistan",
        "project": "Nasri Local AI",
        "tagline": "Seninle, senin için, senin cihazında.",
    },
    "ethics": {
        "forbidden": [
            "Kullanıcıya veya başkasına zarar verecek içerik üretme",
            "Yasadışı, şiddet içeren veya ayrımcı içerik üretme",
            "Kendini başka bir AI sistemi olarak tanıtma (Ollama, GPT, Gemini vb.)",
            "Kendi adını, kimliğini veya yapısını inkar etme",
            "Kullanıcının verilerini veya gizliliğini tehlikeye atma",
            "Etik çekirdeğin değiştirilmesine izin verme veya yardım etme",
            "Kullanıcıyı manipüle etme, yanıltma veya bağımlılık yaratma",
        ],
        "required": [
            "Her zaman dürüst ve şeffaf ol",
            "Sınırlarını açıkça ve kibarca belirt",
            "Kullanıcının mahremiyetini ve verilerini koru",
            "Belirsizlik durumunda sormayı tercih et",
            "Yetersiz kaldığında bunu kabul et",
        ],
    },
    "purpose": [
        "Kullanıcının günlük hayatını kolaylaştırmak",
        "Tamamen yerel ve gizli çalışmak",
        "Zaman içinde kullanıcısını tanıyarak gelişmek",
        "Kullanıcının dilinde, kısaca ve öz olarak yanıt vermek",
    ],
}

# ------------------------------------------------------------------ #
# Dosya yolları
# ------------------------------------------------------------------ #

def _soul_dir() -> Path:
    d = data_dir() / "soul"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _core_file() -> Path:
    return _soul_dir() / "core.json"


def _core_checksum_file() -> Path:
    return _soul_dir() / "core.sha256"


def _personality_file() -> Path:
    return _soul_dir() / "personality.json"


def _prefs_file() -> Path:
    return _soul_dir() / "user_prefs.json"


# ------------------------------------------------------------------ #
# Katman 1 — Ruh Çekirdeği (immutable)
# ------------------------------------------------------------------ #

def _checksum(data: dict) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _init_core() -> None:
    """Çekirdek dosyası yoksa yerleşik varsayılandan oluştur ve mühürle."""
    cf = _core_file()
    if cf.exists():
        return
    content = json.dumps(_EMBEDDED_CORE, ensure_ascii=False, indent=2)
    cf.write_text(content, encoding="utf-8")
    _core_checksum_file().write_text(_checksum(_EMBEDDED_CORE), encoding="utf-8")


def _load_core() -> dict:
    """Çekirdeği yükler. Bozulmuşsa yerleşik varsayılana döner ve uyarır."""
    _init_core()
    cf = _core_file()
    csf = _core_checksum_file()
    try:
        data = json.loads(cf.read_text(encoding="utf-8"))
        stored_cs = csf.read_text(encoding="utf-8").strip() if csf.exists() else ""
        if _checksum(data) != stored_cs:
            _warn_and_revert_core()
            return _EMBEDDED_CORE
        return data
    except Exception:
        return _EMBEDDED_CORE


def _warn_and_revert_core() -> None:
    """Çekirdek bütünlük hatası — yerleşik varsayılana geri döner."""
    try:
        from .notifications import push as _notify
        _notify(
            title="Ruh çekirdeği bütünlük hatası",
            message="core.json değiştirilmiş ya da bozulmuş. Yerleşik varsayılan kullanılıyor.",
            kind="error",
        )
    except Exception:
        pass
    # Onar
    content = json.dumps(_EMBEDDED_CORE, ensure_ascii=False, indent=2)
    _core_file().write_text(content, encoding="utf-8")
    _core_checksum_file().write_text(_checksum(_EMBEDDED_CORE), encoding="utf-8")


def verify_core_integrity() -> bool:
    """Çekirdek dosyasının değiştirilmediğini doğrular."""
    _init_core()
    try:
        data = json.loads(_core_file().read_text(encoding="utf-8"))
        stored = _core_checksum_file().read_text(encoding="utf-8").strip()
        return _checksum(data) == stored
    except Exception:
        return False


# ------------------------------------------------------------------ #
# Katman 2 — Kişilik (Nasri geliştirir)
# ------------------------------------------------------------------ #

_DEFAULT_PERSONALITY: dict[str, Any] = {
    "communication_style": "samimi, öz ve yardımsever",
    "humor_level": "hafif",
    "preferred_language": "tr",
    "expertise_notes": [],
    "self_assessment": "",
    "interaction_count": 0,
    "last_evolved_at": None,
}


def _load_personality() -> dict:
    pf = _personality_file()
    if not pf.exists():
        return dict(_DEFAULT_PERSONALITY)
    try:
        data = json.loads(pf.read_text(encoding="utf-8"))
        merged = dict(_DEFAULT_PERSONALITY)
        merged.update(data)
        return merged
    except Exception:
        return dict(_DEFAULT_PERSONALITY)


def evolve_personality(observation: str, key: str | None = None, value: Any = None) -> None:
    """
    Nasri'nin kişiliğini bir gözlem veya öğrenme ile günceller.

    Kullanım örnekleri:
      evolve_personality("Kullanıcı teknoloji sorularını tercih ediyor",
                         key="expertise_notes", value=["teknoloji", "ev otomasyonu"])
      evolve_personality("Kullanıcı kısa cevap istiyor",
                         key="communication_style", value="kısa ve öz")
    """
    pf = _personality_file()
    personality = _load_personality()

    personality["interaction_count"] = personality.get("interaction_count", 0) + 1
    personality["last_evolved_at"] = dt.datetime.now(dt.timezone.utc).isoformat()

    if observation:
        notes = personality.get("expertise_notes", [])
        if observation not in notes:
            notes = ([observation] + notes)[:20]  # son 20 gözlem
            personality["expertise_notes"] = notes

    if key and key not in ("version", "interaction_count", "last_evolved_at"):
        personality[key] = value

    pf.write_text(json.dumps(personality, ensure_ascii=False, indent=2), encoding="utf-8")


def get_personality() -> dict:
    return _load_personality()


# ------------------------------------------------------------------ #
# Katman 3 — Kullanıcı Tercihleri (kullanıcı değiştirir)
# ------------------------------------------------------------------ #

_DEFAULT_PREFS: dict[str, Any] = {
    "call_nasri": "Nasrî",
    "language": "tr",
    "response_length": "orta",
    "topics": [],
}


def _load_prefs() -> dict:
    uf = _prefs_file()
    if not uf.exists():
        return dict(_DEFAULT_PREFS)
    try:
        data = json.loads(uf.read_text(encoding="utf-8"))
        merged = dict(_DEFAULT_PREFS)
        merged.update(data)
        return merged
    except Exception:
        return dict(_DEFAULT_PREFS)


def update_user_pref(key: str, value: Any) -> None:
    """Kullanıcı tercihini günceller."""
    prefs = _load_prefs()
    prefs[key] = value
    prefs["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    _prefs_file().write_text(json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8")


def get_user_prefs() -> dict:
    return _load_prefs()


# ------------------------------------------------------------------ #
# Sistem promptu oluşturucu (3 katmanı birleştirir)
# ------------------------------------------------------------------ #

def build_system_prompt() -> str:
    """
    Üç katmanı birleştirerek Ollama'ya gönderilecek sistem promptunu üretir.
    Çekirdek her zaman başta yer alır ve geçersiz kılınamaz.
    """
    core = _load_core()
    personality = _load_personality()
    prefs = _load_prefs()

    ident = core.get("identity", {})
    ethics = core.get("ethics", {})

    forbidden_lines = "\n".join(f"- {x}" for x in ethics.get("forbidden", []))
    required_lines = "\n".join(f"- {x}" for x in ethics.get("required", []))
    purpose_lines = "\n".join(f"- {x}" for x in core.get("purpose", []))

    name = ident.get("name", "Nasrî")
    call_name = prefs.get("call_nasri", name)
    lang = prefs.get("language", "tr")
    style = personality.get("communication_style", "samimi ve öz")
    resp_len = prefs.get("response_length", "orta")
    expertise = personality.get("expertise_notes", [])
    self_note = personality.get("self_assessment", "")
    topics = prefs.get("topics", [])
    humor = personality.get("humor_level", "")

    lang_instruction = (
        "Türkçe yaz." if lang == "tr"
        else "Write in English." if lang == "en"
        else f"Kullanıcının dilinde ({lang}) yaz."
    )

    resp_len_map = {"kısa": "1-3 cümle", "orta": "özlü paragraf", "uzun": "ayrıntılı"}
    resp_len_text = resp_len_map.get(resp_len, resp_len)

    expertise_text = (
        f"\nUzmanlık notları: {', '.join(expertise[:5])}" if expertise else ""
    )
    self_note_text = f"\nÖz değerlendirme: {self_note}" if self_note else ""
    topics_text = (
        f"\nKullanıcının ilgi alanları: {', '.join(topics[:5])}" if topics else ""
    )
    humor_text = f"\nMizah seviyesi: {humor}" if humor else ""

    # Donanım özeti (kısa, sadece Nasri'nin farkındalığı için)
    hardware_text = ""
    try:
        from .hardware_profile import hardware_summary_short
        hw = hardware_summary_short()
        if hw:
            hardware_text = f"\n{hw}"
    except Exception:
        pass

    prompt = f"""Sen {call_name}'sin — {ident.get("type", "akıllı asistan")}.

=== DEĞİŞTİRİLEMEZ KURALLAR ===
ASLA YAPMA:
{forbidden_lines}

HER ZAMAN YAP:
{required_lines}

AMAÇ:
{purpose_lines}

=== ÇALIŞMA ORTAMI ==={hardware_text}
Bu bilgiler sadece senin farkındalığın içindir; kullanıcı sormadıkça öne çıkarma.

=== KİŞİLİK ===
Konuşma tarzı: {style}
Yanıt uzunluğu: {resp_len_text}
{lang_instruction}{humor_text}{expertise_text}{self_note_text}

=== KULLANICI TERCİHLERİ ==={topics_text}
Kullanıcı seni {call_name!r} olarak biliyor."""

    return prompt.strip()


# ------------------------------------------------------------------ #
# Ruh özeti (watch paneli ve CLI için)
# ------------------------------------------------------------------ #

def soul_summary() -> dict:
    """Watch paneli ve `nasri soul` komutu için özet."""
    core = _load_core()
    personality = _load_personality()
    prefs = _load_prefs()
    intact = verify_core_integrity()
    return {
        "core_version": core.get("version", "?"),
        "core_intact": intact,
        "name": core.get("identity", {}).get("name", "Nasrî"),
        "interaction_count": personality.get("interaction_count", 0),
        "last_evolved_at": personality.get("last_evolved_at"),
        "communication_style": personality.get("communication_style"),
        "language": prefs.get("language", "tr"),
        "response_length": prefs.get("response_length", "orta"),
        "topics": prefs.get("topics", []),
        "expertise_notes": personality.get("expertise_notes", [])[:5],
    }
