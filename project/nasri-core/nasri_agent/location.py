"""
location.py — Nasrî Konum ve Saat Dilimi Otomatik Tespiti

İlk kurulumda ve periyodik olarak cihazın gerçek konumunu ve saat dilimini
IP tabanlı geolokasyon ile tespit eder; NASRI_TIMEZONE değişkenini .env'e
otomatik olarak yazar.

Kaynak sıralaması (HTTPS önceliği, anahtar gerekmez):
  1. ipapi.co       — HTTPS, ~1000 istek/gün
  2. freeipapi.com  — HTTPS, 60 istek/dakika
  3. ip-api.com     — HTTP,  45 istek/dakika
  4. worldtimeapi.org — yedek, sadece timezone

Konum değişim tespiti:
  - Önceki konumla mesafe > 200 km VEYA timezone string değişmişse
  - .env güncellenir ve .restart_flag yazılır (servis kendisi yeniden başlar)
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .config import data_dir, install_dir

# ------------------------------------------------------------------ #
# Veri dosyaları
# ------------------------------------------------------------------ #

def _location_file() -> Path:
    return data_dir() / "location.json"


def _env_file() -> Path:
    return install_dir() / "project" / "nasri-core" / ".env"


# ------------------------------------------------------------------ #
# Önbellek
# ------------------------------------------------------------------ #

def _load_cached() -> dict:
    f = _location_file()
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cached(data: dict) -> None:
    f = _location_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ------------------------------------------------------------------ #
# Geolokasyon kaynakları
# ------------------------------------------------------------------ #

def _http_get(url: str, timeout: int = 8) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Nasri/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return json.loads(r.read().decode("utf-8", errors="replace"))


def _query_ipapi_co() -> dict | None:
    """ipapi.co — HTTPS, anahtar yok, ~1000/gün."""
    try:
        data = _http_get("https://ipapi.co/json/")
        tz = data.get("timezone", "")
        if not tz:
            return None
        return {
            "timezone": tz,
            "city": data.get("city", ""),
            "country": data.get("country_name", ""),
            "country_code": data.get("country_code", ""),
            "lat": float(data.get("latitude") or 0),
            "lon": float(data.get("longitude") or 0),
            "public_ip": data.get("ip", ""),
            "source": "ipapi.co",
        }
    except Exception:
        return None


def _query_freeipapi() -> dict | None:
    """freeipapi.com — HTTPS, anahtar yok, 60/dk."""
    try:
        data = _http_get("https://freeipapi.com/api/json/")
        tz = data.get("timeZone", "")
        if not tz:
            return None
        return {
            "timezone": tz,
            "city": data.get("cityName", ""),
            "country": data.get("countryName", ""),
            "country_code": data.get("countryCode", ""),
            "lat": float(data.get("latitude") or 0),
            "lon": float(data.get("longitude") or 0),
            "public_ip": data.get("ipAddress", ""),
            "source": "freeipapi.com",
        }
    except Exception:
        return None


def _query_ip_api() -> dict | None:
    """ip-api.com — HTTP, anahtar yok, 45/dk."""
    try:
        data = _http_get(
            "http://ip-api.com/json/?fields=status,timezone,city,country,countryCode,lat,lon,query"
        )
        if data.get("status") != "success":
            return None
        tz = data.get("timezone", "")
        if not tz:
            return None
        return {
            "timezone": tz,
            "city": data.get("city", ""),
            "country": data.get("country", ""),
            "country_code": data.get("countryCode", ""),
            "lat": float(data.get("lat") or 0),
            "lon": float(data.get("lon") or 0),
            "public_ip": data.get("query", ""),
            "source": "ip-api.com",
        }
    except Exception:
        return None


def _query_worldtimeapi() -> dict | None:
    """worldtimeapi.org — yedek, sadece timezone döner."""
    try:
        data = _http_get("http://worldtimeapi.org/api/ip")
        tz = data.get("timezone", "")
        if not tz:
            return None
        return {
            "timezone": tz,
            "city": "",
            "country": "",
            "country_code": "",
            "lat": 0.0,
            "lon": 0.0,
            "public_ip": data.get("client_ip", ""),
            "source": "worldtimeapi.org",
        }
    except Exception:
        return None


# ------------------------------------------------------------------ #
# Ana tespit fonksiyonu
# ------------------------------------------------------------------ #

def detect_location() -> dict | None:
    """
    Sırayla kaynaklara sorarak konum ve timezone bilgisi döner.
    İnternet yoksa None döner.
    """
    for fn in (_query_ipapi_co, _query_freeipapi, _query_ip_api, _query_worldtimeapi):
        result = fn()
        if result and result.get("timezone"):
            import datetime as _dt
            result["detected_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
            return result
    return None


# ------------------------------------------------------------------ #
# Mesafe hesabı
# ------------------------------------------------------------------ #

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """İki koordinat arasındaki mesafeyi km cinsinden döner."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ------------------------------------------------------------------ #
# .env güncelleme
# ------------------------------------------------------------------ #

def _upsert_env(key: str, value: str) -> bool:
    """
    .env dosyasında key=value satırını günceller veya ekler.
    Dosya yoksa oluşturmaz (servis kurulumu yapılmamış olabilir).
    """
    env = _env_file()
    if not env.exists():
        return False
    lines = env.read_text(encoding="utf-8").splitlines()
    prefix = f"{key}="
    replaced = False
    out = []
    for line in lines:
        if line.strip().startswith(prefix):
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"{key}={value}")
    env.write_text("\n".join(out) + "\n", encoding="utf-8")
    return True


def _read_env_timezone() -> str:
    """Mevcut .env dosyasından NASRI_TIMEZONE değerini okur."""
    env = _env_file()
    if not env.exists():
        return ""
    for line in env.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("NASRI_TIMEZONE="):
            val = stripped[len("NASRI_TIMEZONE="):].strip()
            # Boş veya yorum değeri sayma
            return val if val and not val.startswith("#") else ""
    return ""


# ------------------------------------------------------------------ #
# Periyodik kontrol
# ------------------------------------------------------------------ #

_RECHECK_INTERVAL_HOURS = 6
_LOCATION_CHANGE_KM_THRESHOLD = 200  # km


def should_recheck(interval_hours: int = _RECHECK_INTERVAL_HOURS) -> bool:
    cached = _load_cached()
    last = cached.get("detected_at")
    if not last:
        return True
    try:
        import datetime as _dt
        ts = _dt.datetime.fromisoformat(last)
        elapsed = (_dt.datetime.now(_dt.timezone.utc) - ts).total_seconds()
        return elapsed > interval_hours * 3600
    except Exception:
        return True


def run_location_check(force: bool = False, verbose: bool = True) -> dict | None:
    """
    Konum tespiti ve saat dilimi güncelleme ana fonksiyonu.

    1. Gerekli değilse atlar (interval_hours dolmamışsa)
    2. IP tabanlı geolokasyon yapar
    3. Önceki konumla karşılaştırır
    4. Timezone değiştiyse .env günceller + .restart_flag yazar
    5. Sonucu diske kaydeder

    Returns:
        Tespit edilen konum dict'i (veya None)
    """
    def log(msg: str) -> None:
        if verbose:
            print(f"[nasri/location] {msg}")

    if not force and not should_recheck():
        return _load_cached()

    log("Konum tespiti yapılıyor...")
    result = detect_location()
    if not result:
        log("Konum tespit edilemedi (internet bağlantısı olmayabilir).")
        return _load_cached() or None

    new_tz = result["timezone"]
    new_city = result.get("city", "?")
    new_country = result.get("country", "?")
    source = result.get("source", "?")
    log(f"Tespit: {new_city}, {new_country} → {new_tz} ({source})")

    cached = _load_cached()
    old_tz = cached.get("timezone", "")
    timezone_changed = old_tz and old_tz != new_tz

    # Mesafe kontrolü (koordinatlar varsa)
    distance_km = 0.0
    if cached.get("lat") and cached.get("lon") and result.get("lat") and result.get("lon"):
        distance_km = _haversine(
            cached["lat"], cached["lon"],
            result["lat"], result["lon"],
        )

    location_moved = distance_km > _LOCATION_CHANGE_KM_THRESHOLD

    if timezone_changed or location_moved:
        reason = f"timezone değişti ({old_tz} → {new_tz})" if timezone_changed else f"konum değişti ({distance_km:.0f} km)"
        log(f"Konum değişimi algılandı: {reason}")
        _apply_timezone(new_tz, log)
    elif not old_tz:
        # İlk tespit — hemen yaz
        log(f"İlk konum tespiti: {new_tz}")
        _apply_timezone(new_tz, log)
    else:
        env_tz = _read_env_timezone()
        if env_tz != new_tz:
            # .env güncel değil
            log(f".env timezone uyuşmuyor ({env_tz} → {new_tz}), güncelleniyor...")
            _apply_timezone(new_tz, log)
        else:
            log(f"Timezone değişmemiş: {new_tz}")

    _save_cached(result)
    return result


def _apply_timezone(timezone: str, log: Any) -> None:
    """
    Timezone'u üç katmanda uygular:
    1. .env dosyasına NASRI_TIMEZONE yazar (servis yeniden başlatılır)
    2. Sistem saat dilimini OS düzeyinde ayarlamayı dener (root/sudo gerekebilir)
    3. Başarısız olursa os.environ ile süreç düzeyinde uygular
    """
    written = _upsert_env("NASRI_TIMEZONE", timezone)
    if written:
        log(f".env güncellendi: NASRI_TIMEZONE={timezone}")
        try:
            flag = data_dir() / ".restart_flag"
            flag.touch()
            log("Servis yeniden başlatma sinyali gönderildi.")
        except Exception:
            pass
    else:
        log(f".env bulunamadı, NASRI_TIMEZONE={timezone} uygulanamadı (os.environ kullanılıyor).")
        os.environ["NASRI_TIMEZONE"] = timezone

    # OS sistem saat dilimini de güncelle
    try:
        from .time_sync import _try_fix_timezone
        if _try_fix_timezone(timezone):
            log(f"Sistem saat dilimi güncellendi: {timezone}")
        else:
            log(f"Sistem saat dilimi güncellenemedi (root/sudo gerekebilir). NASRI_TIMEZONE={timezone} kullanılacak.")
    except Exception as exc:
        log(f"Sistem saat dilimi güncelleme hatası: {exc}")


def get_location_summary() -> str:
    """Tek satırlık konum özeti (durum paneli için)."""
    cached = _load_cached()
    if not cached:
        return "Konum bilinmiyor"
    city = cached.get("city", "?")
    country = cached.get("country", "?")
    tz = cached.get("timezone", "?")
    return f"{city}, {country} ({tz})"
