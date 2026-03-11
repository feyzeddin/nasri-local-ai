"""
time_sync.py — Nasrî'nin Zaman Farkındalığı

Görevler:
  1. Sistem saatinin güvenilirliğini doğrular (NTP senkronu kontrolü)
  2. Saat şüpheliyse (yıl < 2025) otomatik NTP senkronu tetikler
  3. Her sorgu öncesi Ollama'ya güncel tarih/saat bağlamı sağlar
  4. Timezone'u otomatik tespit eder

Platform:
  Linux  — timedatectl + systemd-timesyncd / ntpdate
  macOS  — sntp
  Windows— w32tm
"""
from __future__ import annotations

import datetime as dt
import os
import platform
import shutil
import subprocess
from pathlib import Path

# ------------------------------------------------------------------ #
# Türkçe tarih formatlama
# ------------------------------------------------------------------ #

_TR_WEEKDAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
_TR_MONTHS   = [
    "", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]


def _get_timezone_name() -> str:
    """Sistemin zaman dilimini okur."""
    # Linux: /etc/timezone
    try:
        tz = Path("/etc/timezone").read_text(encoding="utf-8").strip()
        if tz:
            return tz
    except Exception:
        pass
    # TZ env
    tz_env = os.getenv("TZ", "")
    if tz_env:
        return tz_env
    # zoneinfo (Python 3.9+)
    try:
        import zoneinfo
        localzone = dt.datetime.now().astimezone().tzname()
        if localzone:
            return localzone
    except Exception:
        pass
    # Windows: registry veya tzname
    if platform.system() == "Windows":
        try:
            import winreg  # type: ignore
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\TimeZoneInformation",
            ) as key:
                return winreg.QueryValueEx(key, "TimeZoneKeyName")[0]
        except Exception:
            pass
    return dt.datetime.now().astimezone().tzname() or "UTC"


def get_current_datetime() -> dt.datetime:
    """Yerel saat diliminde şimdiki zamanı döner."""
    return dt.datetime.now().astimezone()


def format_datetime_tr(moment: dt.datetime | None = None) -> str:
    """
    Türkçe okunabilir tarih/saat metni üretir.
    Örnek: "Çarşamba, 11 Mart 2026, 16:24 (Europe/Istanbul)"
    """
    if moment is None:
        moment = get_current_datetime()
    weekday = _TR_WEEKDAYS[moment.weekday()]
    month   = _TR_MONTHS[moment.month]
    tz_name = _get_timezone_name()
    return (
        f"{weekday}, {moment.day} {month} {moment.year}, "
        f"{moment.strftime('%H:%M')} ({tz_name})"
    )


def get_context_line() -> str:
    """
    Ollama sistem promptuna eklenen tek satırlık zaman bağlamı.
    Her sorgu çağrısında taze hesaplanır.
    """
    return f"Şu anki tarih ve saat: {format_datetime_tr()}"


# ------------------------------------------------------------------ #
# Saat güvenilirliği kontrolü
# ------------------------------------------------------------------ #

_MIN_PLAUSIBLE_YEAR = 2025
_MAX_PLAUSIBLE_YEAR = 2100


def is_time_plausible() -> bool:
    """
    Sistem saatinin mantıklı aralıkta olup olmadığını kontrol eder.
    Eğitim kesim tarihi (2024) veya çok gelecek → şüpheli.
    """
    year = dt.datetime.now().year
    return _MIN_PLAUSIBLE_YEAR <= year <= _MAX_PLAUSIBLE_YEAR


def _check_ntp_sync_linux() -> bool:
    """Linux: systemd-timesyncd / chrony senkron durumunu kontrol eder."""
    if shutil.which("timedatectl"):
        out = _run(["timedatectl", "show", "--property=NTPSynchronized,Timezone"])
        return "NTPSynchronized=yes" in out
    return False


def _run(args: list[str], timeout: int = 15) -> str:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def check_ntp_sync() -> bool:
    """Sistemin NTP ile senkronize olup olmadığını döner."""
    sys = platform.system()
    if sys == "Linux":
        return _check_ntp_sync_linux()
    if sys == "Windows":
        out = _run(["w32tm", "/query", "/status"])
        return "Leap Indicator: 0" in out or "Source:" in out
    if sys == "Darwin":
        out = _run(["systemsetup", "-getnetworktimeserver"])
        return "networktimeserver" in out.lower()
    return True  # bilinmeyen platformda varsayılan: güven


def force_ntp_sync() -> bool:
    """
    NTP senkronunu zorla. Başarılıysa True döner.
    Kullanıcı onayı veya etkileşimi gerektirmez.
    """
    sys = platform.system()
    try:
        if sys == "Linux":
            # 1. Önce systemd-timesyncd aç (en güvenli)
            if shutil.which("timedatectl"):
                subprocess.run(
                    ["timedatectl", "set-ntp", "true"],
                    timeout=10,
                    capture_output=True,
                )
                # Senkronu hemen tetikle (chrony varsa)
                if shutil.which("chronyc"):
                    subprocess.run(
                        ["chronyc", "makestep"],
                        timeout=10,
                        capture_output=True,
                    )
                return True
            # 2. ntpdate fallback
            if shutil.which("ntpdate"):
                r = subprocess.run(
                    ["ntpdate", "-u", "pool.ntp.org"],
                    timeout=30,
                    capture_output=True,
                )
                return r.returncode == 0
        elif sys == "Darwin":
            if shutil.which("sntp"):
                r = subprocess.run(
                    ["sntp", "-sS", "pool.ntp.org"],
                    timeout=30,
                    capture_output=True,
                )
                return r.returncode == 0
        elif sys == "Windows":
            r = subprocess.run(
                ["w32tm", "/resync", "/force"],
                timeout=30,
                capture_output=True,
            )
            return r.returncode == 0
    except Exception:
        pass
    return False


# ------------------------------------------------------------------ #
# Başlangıç kontrolü (service.py tarafından çağrılır)
# ------------------------------------------------------------------ #

def ensure_time_accurate(verbose: bool = True) -> None:
    """
    Servis başlangıcında çağrılır.
    1. Saat mantıklı mı kontrol et
    2. NTP senkronu var mı kontrol et
    3. Gerekirse senkronla
    Kullanıcıdan onay istemez, tamamen otomatik.
    """
    def log(msg: str) -> None:
        if verbose:
            print(f"[nasri/time] {msg}")

    now_str = format_datetime_tr()
    log(f"Yerel saat: {now_str}")

    if not is_time_plausible():
        log(f"UYARI: Sistem saati şüpheli (yıl={dt.datetime.now().year}). NTP senkronu tetikleniyor...")
        ok = force_ntp_sync()
        if ok:
            log(f"NTP senkronu başarılı. Yeni saat: {format_datetime_tr()}")
            try:
                from .notifications import push as _notify
                _notify(
                    title="Sistem saati güncellendi",
                    message=f"Saat NTP ile düzeltildi: {format_datetime_tr()}",
                    kind="info",
                )
            except Exception:
                pass
        else:
            log("NTP senkronu başarısız. Sistem saati hatalı olabilir.")
            try:
                from .notifications import push as _notify
                _notify(
                    title="Sistem saati hatalı olabilir",
                    message=(
                        f"Mevcut saat: {format_datetime_tr()} — "
                        "NTP senkronu başarısız. İnternet bağlantısını kontrol edin."
                    ),
                    kind="warning",
                )
            except Exception:
                pass
        return

    # Saat makul ama NTP senkronu yok mu?
    if not check_ntp_sync():
        log("NTP senkronu etkin değil. Aktifleştiriliyor...")
        ok = force_ntp_sync()
        log("NTP aktifleştirildi." if ok else "NTP etkinleştirilemedi (sudo gerekebilir).")
    else:
        log("NTP senkronu aktif ve saat doğru.")
