"""
time_sync.py — Nasrî'nin Zaman Farkındalığı

Görevler:
  1. NTP sunucusuna doğrudan UDP ile bağlanarak gerçek zamanı okur
  2. Sistem saati ile farkı (offset) hesaplar ve önbelleğe alır
  3. Her tarih/saat sorgusunda offset uygulanmış doğru zamanı döner
  4. Sistem saatini düzeltemese bile (sudo yok) Ollama'ya doğru zaman gider
  5. Sistem saatini düzeltmeyi de dener (timedatectl / ntpdate / chronyc)

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
import socket
import struct
import subprocess
import time
from pathlib import Path

# ------------------------------------------------------------------ #
# Türkçe tarih formatlama
# ------------------------------------------------------------------ #

_TR_WEEKDAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
_TR_MONTHS   = [
    "", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]

# Sistem saati ile NTP arasındaki fark (saniye). 0 = güvenilir veya henüz ölçülmedi.
_ntp_offset: float = 0.0
_ntp_last_checked: float = 0.0
_NTP_CHECK_INTERVAL = 3600  # 1 saatte bir yeniden kontrol

_NTP_SERVERS = [
    "pool.ntp.org",
    "time.cloudflare.com",
    "time.google.com",
    "tr.pool.ntp.org",
]


def _get_ntp_time(server: str = "pool.ntp.org", timeout: int = 5) -> float | None:
    """
    NTP sunucusuna ham UDP paketiyle bağlanır, gerçek Unix zamanını döner.
    Ekstra Python paketi veya sistem izni gerektirmez.
    """
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.settimeout(timeout)
        # RFC 4330 uyumlu basit NTP istek paketi
        data = b"\x1b" + 47 * b"\x00"
        client.sendto(data, (server, 123))
        data, _ = client.recvfrom(1024)
        client.close()
        if len(data) < 48:
            return None
        # Bytes 40-47: Transmit Timestamp (seconds since Jan 1 1900)
        t = struct.unpack("!12I", data)[10]
        # NTP epoch (1900) → Unix epoch (1970): 70 yıl = 2208988800 saniye
        return float(t - 2208988800)
    except Exception:
        return None


def _query_ntp_offset() -> float:
    """
    Birden fazla NTP sunucusunu dener, sistem saati ile farkı (saniye) döner.
    Başarısız olursa 0.0 döner.
    """
    sys_time = time.time()
    for server in _NTP_SERVERS:
        ntp_time = _get_ntp_time(server)
        if ntp_time is not None:
            return ntp_time - sys_time
    return 0.0


def refresh_ntp_offset() -> float:
    """NTP offset'ini tazeler ve önbelleğe alır. Güncel offset'i döner."""
    global _ntp_offset, _ntp_last_checked
    _ntp_offset = _query_ntp_offset()
    _ntp_last_checked = time.time()
    return _ntp_offset


def _get_configured_tz() -> "dt.tzinfo | None":
    """
    NASRI_TIMEZONE env değişkeninden zoneinfo nesnesi döner.
    Ayarlı değilse None döner (sistem saati dilimi kullanılır).
    """
    tz_name = os.getenv("NASRI_TIMEZONE", "").strip()
    if not tz_name:
        return None
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz_name)
    except Exception:
        try:
            import datetime as _dt
            return _dt.timezone(
                _dt.timedelta(hours=int(tz_name.replace("UTC", "").replace("+", "") or 0))
            )
        except Exception:
            return None


def _get_timezone_name() -> str:
    """Sistemin (veya NASRI_TIMEZONE ile ayarlanan) zaman dilimini döner."""
    # 1. NASRI_TIMEZONE env'i (en yüksek öncelik)
    tz_env = os.getenv("NASRI_TIMEZONE", "").strip()
    if tz_env:
        return tz_env
    # 2. /etc/timezone (Linux)
    try:
        tz = Path("/etc/timezone").read_text(encoding="utf-8").strip()
        if tz:
            return tz
    except Exception:
        pass
    # 3. TZ env
    tz_env2 = os.getenv("TZ", "")
    if tz_env2:
        return tz_env2
    # 4. Windows registry
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
    """
    NTP offset uygulanmış doğru zamanı döner.
    NASRI_TIMEZONE veya sistem saat diliminde gösterir.
    """
    now_unix = time.time() + _ntp_offset
    tz = _get_configured_tz()
    if tz is not None:
        return dt.datetime.fromtimestamp(now_unix, tz=tz)
    return dt.datetime.fromtimestamp(now_unix).astimezone()


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
# Sistem saati düzeltme (sudo gerekebilir — başarısız olursa offset kullanılır)
# ------------------------------------------------------------------ #

_MIN_PLAUSIBLE_YEAR = 2025
_MAX_PLAUSIBLE_YEAR = 2100


def is_time_plausible() -> bool:
    year = dt.datetime.now().year
    return _MIN_PLAUSIBLE_YEAR <= year <= _MAX_PLAUSIBLE_YEAR


def _run(args: list[str], timeout: int = 15) -> str:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def _check_ntp_sync_linux() -> bool:
    if shutil.which("timedatectl"):
        out = _run(["timedatectl", "show", "--property=NTPSynchronized,Timezone"])
        return "NTPSynchronized=yes" in out
    return False


def check_ntp_sync() -> bool:
    sys = platform.system()
    if sys == "Linux":
        return _check_ntp_sync_linux()
    if sys == "Windows":
        out = _run(["w32tm", "/query", "/status"])
        return "Leap Indicator: 0" in out or "Source:" in out
    if sys == "Darwin":
        out = _run(["systemsetup", "-getnetworktimeserver"])
        return "networktimeserver" in out.lower()
    return True


def _sudo_run(args: list[str], timeout: int = 30) -> bool:
    """Komutu önce doğrudan, başarısız olursa sudo -n ile çalıştırır."""
    try:
        r = subprocess.run(args, capture_output=True, timeout=timeout)
        if r.returncode == 0:
            return True
    except Exception:
        pass
    if shutil.which("sudo"):
        try:
            r2 = subprocess.run(["sudo", "-n"] + args, capture_output=True, timeout=timeout)
            return r2.returncode == 0
        except Exception:
            pass
    return False


def _try_fix_system_clock() -> bool:
    """
    Sistem saatini NTP ile senkronize etmeyi dener.
    Her komut önce doğrudan, başarısız olursa sudo -n ile denenir.
    """
    sys = platform.system()
    try:
        if sys == "Linux":
            if shutil.which("timedatectl"):
                _sudo_run(["timedatectl", "set-ntp", "true"], timeout=10)
                if shutil.which("chronyc"):
                    _sudo_run(["chronyc", "makestep"], timeout=10)
                elif shutil.which("ntpdate"):
                    _sudo_run(["ntpdate", "-u", "pool.ntp.org"], timeout=30)
                return True
            if shutil.which("ntpdate"):
                return _sudo_run(["ntpdate", "-u", "pool.ntp.org"], timeout=30)
        elif sys == "Darwin":
            if shutil.which("sntp"):
                return _sudo_run(["sntp", "-sS", "pool.ntp.org"], timeout=30)
        elif sys == "Windows":
            r = subprocess.run(
                ["w32tm", "/resync", "/force"],
                timeout=30, capture_output=True,
            )
            return r.returncode == 0
    except Exception:
        pass
    return False


# ------------------------------------------------------------------ #
# Başlangıç + periyodik kontrol (service.py tarafından çağrılır)
# ------------------------------------------------------------------ #

# IANA timezone → Windows timezone adı eşleştirmesi
_IANA_TO_WINDOWS: dict[str, str] = {
    "Europe/Istanbul":        "Turkey Standard Time",
    "Europe/London":          "GMT Standard Time",
    "Europe/Paris":           "Romance Standard Time",
    "Europe/Berlin":          "W. Europe Standard Time",
    "Europe/Amsterdam":       "W. Europe Standard Time",
    "Europe/Rome":            "W. Europe Standard Time",
    "Europe/Madrid":          "Romance Standard Time",
    "Europe/Warsaw":          "Central European Standard Time",
    "Europe/Athens":          "GTB Standard Time",
    "Europe/Bucharest":       "GTB Standard Time",
    "Europe/Helsinki":        "FLE Standard Time",
    "Europe/Kyiv":            "FLE Standard Time",
    "Europe/Moscow":          "Russian Standard Time",
    "America/New_York":       "Eastern Standard Time",
    "America/Chicago":        "Central Standard Time",
    "America/Denver":         "Mountain Standard Time",
    "America/Los_Angeles":    "Pacific Standard Time",
    "America/Sao_Paulo":      "E. South America Standard Time",
    "America/Argentina/Buenos_Aires": "Argentina Standard Time",
    "America/Mexico_City":    "Central Standard Time (Mexico)",
    "America/Bogota":         "SA Pacific Standard Time",
    "Asia/Tokyo":             "Tokyo Standard Time",
    "Asia/Shanghai":          "China Standard Time",
    "Asia/Hong_Kong":         "China Standard Time",
    "Asia/Singapore":         "Singapore Standard Time",
    "Asia/Kolkata":           "India Standard Time",
    "Asia/Dubai":             "Arabian Standard Time",
    "Asia/Riyadh":            "Arab Standard Time",
    "Asia/Tehran":            "Iran Standard Time",
    "Asia/Baku":              "Azerbaijan Standard Time",
    "Asia/Tbilisi":           "Georgian Standard Time",
    "Asia/Yerevan":           "Caucasus Standard Time",
    "Asia/Karachi":           "Pakistan Standard Time",
    "Asia/Dhaka":             "Bangladesh Standard Time",
    "Asia/Bangkok":           "SE Asia Standard Time",
    "Asia/Jakarta":           "SE Asia Standard Time",
    "Asia/Seoul":             "Korea Standard Time",
    "Asia/Taipei":            "Taipei Standard Time",
    "Africa/Cairo":           "Egypt Standard Time",
    "Africa/Johannesburg":    "South Africa Standard Time",
    "Africa/Lagos":           "W. Central Africa Standard Time",
    "Africa/Nairobi":         "E. Africa Standard Time",
    "Australia/Sydney":       "AUS Eastern Standard Time",
    "Australia/Melbourne":    "AUS Eastern Standard Time",
    "Australia/Perth":        "W. Australia Standard Time",
    "Pacific/Auckland":       "New Zealand Standard Time",
    "Pacific/Honolulu":       "Hawaiian Standard Time",
    "UTC":                    "UTC",
}


def _try_fix_timezone(timezone: str) -> bool:
    """
    Sistem saat dilimini verilen IANA timezone adına ayarlamayı dener.

    Linux  : timedatectl set-timezone (root/sudo -n ile dener)
             Başarısız olursa /etc/localtime symlink'i dener.
    macOS  : systemsetup -settimezone (sudo -n ile dener)
    Windows: tzutil /s <Windows-tz-adı>

    Başarısız olursa False döner — çağıran NTP offset ile devam eder.
    """
    sys_name = platform.system()
    try:
        if sys_name == "Linux":
            if shutil.which("timedatectl"):
                # Önce doğrudan dene (root ise çalışır)
                r = subprocess.run(
                    ["timedatectl", "set-timezone", timezone],
                    capture_output=True, timeout=10,
                )
                if r.returncode == 0:
                    return True
                # sudo -n ile dene (şifresiz sudo ayarlıysa çalışır)
                if shutil.which("sudo"):
                    r2 = subprocess.run(
                        ["sudo", "-n", "timedatectl", "set-timezone", timezone],
                        capture_output=True, timeout=10,
                    )
                    if r2.returncode == 0:
                        return True
            # timedatectl yoksa veya başarısız olduysa: /etc/localtime symlink'i dene
            zone_file = Path(f"/usr/share/zoneinfo/{timezone}")
            if zone_file.exists():
                localtime = Path("/etc/localtime")
                localtime.unlink(missing_ok=True)
                localtime.symlink_to(zone_file)
                Path("/etc/timezone").write_text(timezone + "\n", encoding="utf-8")
                return True

        elif sys_name == "Darwin":
            if shutil.which("systemsetup"):
                r = subprocess.run(
                    ["systemsetup", "-settimezone", timezone],
                    capture_output=True, timeout=10,
                )
                if r.returncode == 0:
                    return True
                if shutil.which("sudo"):
                    r2 = subprocess.run(
                        ["sudo", "-n", "systemsetup", "-settimezone", timezone],
                        capture_output=True, timeout=10,
                    )
                    if r2.returncode == 0:
                        return True

        elif sys_name == "Windows":
            win_tz = _IANA_TO_WINDOWS.get(timezone)
            if win_tz and shutil.which("tzutil"):
                r = subprocess.run(
                    ["tzutil", "/s", win_tz],
                    capture_output=True, timeout=10,
                )
                return r.returncode == 0

    except Exception:
        pass
    return False


def ensure_time_accurate(verbose: bool = True) -> None:
    """
    Servis başlangıcında ve periyodik olarak çağrılır.
    1. NTP'ye doğrudan bağlanarak offset ölçer (sudo gerektirmez)
    2. Offset > 60s ise sistem saatini düzeltmeyi dener
    3. Sistem saati UTC ise ve NASRI_TIMEZONE ayarlı değilse uyarır
    4. Sistem saati düzeltilemese bile get_current_datetime() doğru zamanı döner
    """
    global _ntp_offset

    def log(msg: str) -> None:
        if verbose:
            print(f"[nasri/time] {msg}")

    sys_now = dt.datetime.now()
    log(f"Sistem saati: {sys_now.strftime('%Y-%m-%d %H:%M:%S')}")

    # Saat dilimi kontrolü
    sys_tz = _get_timezone_name()
    nasri_tz = os.getenv("NASRI_TIMEZONE", "").strip()
    if sys_tz in ("UTC", "Etc/UTC", "Universal") and not nasri_tz:
        log("UYARI: Sistem saat dilimi UTC, NASRI_TIMEZONE ayarlı değil.")
        # Konum önbelleğinden timezone al, yoksa Europe/Istanbul fallback
        detected_tz = ""
        try:
            from .location import _load_cached as _loc_cache
            detected_tz = _loc_cache().get("timezone", "")
        except Exception:
            pass
        fix_tz = detected_tz or "Europe/Istanbul"
        fixed_tz = _try_fix_timezone(fix_tz)
        if fixed_tz:
            log(f"Sistem saat dilimi ayarlandı: {fix_tz}")
        else:
            log(f"Sistem saat dilimi ayarlanamadı (root/sudo gerekebilir): {fix_tz}")

    # NTP offset'i ölç
    log("NTP sunucusuna bağlanılıyor...")
    offset = _query_ntp_offset()
    _ntp_offset = offset
    global _ntp_last_checked
    _ntp_last_checked = time.time()

    corrected = get_current_datetime()
    log(f"Düzeltilmiş saat: {format_datetime_tr(corrected)} (offset: {offset:+.1f}s)")

    abs_offset = abs(offset)
    if abs_offset > 60:
        log(f"UYARI: Sistem saati {abs_offset:.0f}s hatalı. Düzeltme deneniyor...")
        fixed = _try_fix_system_clock()
        if fixed:
            # Sistem saati düzeldiyse offset'i sıfırla
            _ntp_offset = 0.0
            log(f"Sistem saati düzeltildi: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            log(f"Sistem saati düzeltilemedi (sudo gerekebilir). NTP offset ile devam: {offset:+.1f}s")
        try:
            from .notifications import push as _notify
            _notify(
                title="Saat düzeltme" + (" başarılı" if fixed else " — offset ile devam"),
                message=(
                    f"Doğru saat: {format_datetime_tr(corrected)}"
                    if fixed else
                    f"Sistem saati {abs_offset:.0f}s hatalı, NTP offset uygulandı."
                ),
                kind="info" if fixed else "warning",
            )
        except Exception:
            pass
    elif abs_offset > 5:
        log(f"Küçük saat farkı ({offset:+.1f}s) — NTP offset uygulandı, sistem saati değiştirilmedi.")
    else:
        log("Saat doğru.")


def should_recheck_ntp(interval_hours: int = 1) -> bool:
    """NTP kontrolünün yenilenmesi gerekip gerekmediğini döner."""
    if _ntp_last_checked == 0.0:
        return True
    return (time.time() - _ntp_last_checked) > interval_hours * 3600
