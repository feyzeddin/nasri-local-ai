"""
hardware_profile.py — Nasrî'nin Donanım Farkındalığı

Yapılanlar:
  1. Donanım taraması (CPU, RAM, GPU, disk, ağ, USB, OS)
  2. Profili data_dir/hardware_profile.json dosyasına yazar
  3. Önceki taramayla karşılaştırarak değişiklikleri tespit eder
  4. Kısa özet metni sistem promptuna eklenir
  5. 'nasri hardware' CLI komutuyla elle çalıştırılabilir

Platform desteği:
  - Linux  : /proc dosyaları + lspci, lsblk, nvidia-smi, lsusb
  - Windows: psutil + wmic/PowerShell
  - macOS  : psutil + system_profiler
"""
from __future__ import annotations

import datetime as dt
import json
import os
import platform
import subprocess
import shutil
from pathlib import Path
from typing import Any

from .config import data_dir
from .notifications import push as _notify

# ------------------------------------------------------------------ #
# Dosya yolları
# ------------------------------------------------------------------ #

def _profile_file() -> Path:
    return data_dir() / "hardware_profile.json"


def _changes_file() -> Path:
    return data_dir() / "hardware_changes.json"


# ------------------------------------------------------------------ #
# Yardımcı: güvenli subprocess
# ------------------------------------------------------------------ #

def _run(args: list[str], timeout: int = 10) -> str:
    try:
        r = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout
        )
        return r.stdout.strip()
    except Exception:
        return ""


# ------------------------------------------------------------------ #
# OS & platform
# ------------------------------------------------------------------ #

def _scan_os() -> dict[str, Any]:
    info: dict[str, Any] = {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "hostname": platform.node(),
        "python": platform.python_version(),
    }
    # Linux: /etc/os-release için daha güzel isim
    if platform.system() == "Linux":
        try:
            text = Path("/etc/os-release").read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.startswith("PRETTY_NAME="):
                    info["distro"] = line.split("=", 1)[1].strip().strip('"')
                    break
        except Exception:
            pass
        # Kernel versiyonu
        kernel = _run(["uname", "-r"])
        if kernel:
            info["kernel"] = kernel
    return info


# ------------------------------------------------------------------ #
# CPU
# ------------------------------------------------------------------ #

def _scan_cpu() -> dict[str, Any]:
    info: dict[str, Any] = {
        "architecture": platform.machine(),
    }

    # psutil ile temel bilgi
    try:
        import psutil
        freq = psutil.cpu_freq()
        info["cores_physical"] = psutil.cpu_count(logical=False) or 0
        info["cores_logical"] = psutil.cpu_count(logical=True) or 0
        if freq:
            info["freq_max_mhz"] = round(freq.max)
            info["freq_current_mhz"] = round(freq.current)
    except Exception:
        pass

    # Linux: /proc/cpuinfo'dan model adı
    if platform.system() == "Linux":
        try:
            cpuinfo = Path("/proc/cpuinfo").read_text(encoding="utf-8")
            for line in cpuinfo.splitlines():
                if line.startswith("model name"):
                    info["model"] = line.split(":", 1)[1].strip()
                    break
                if line.startswith("Hardware"):  # ARM
                    info["model"] = line.split(":", 1)[1].strip()
                    break
        except Exception:
            pass
        # CPU flags (avx, avx2, aes vb.)
        try:
            flags: list[str] = []
            for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
                if line.startswith("flags"):
                    raw = line.split(":", 1)[1].strip().split()
                    flags = [f for f in ["avx", "avx2", "avx512f", "aes", "sse4_2"] if f in raw]
                    break
            if flags:
                info["features"] = flags
        except Exception:
            pass

    # Windows: WMIC
    elif platform.system() == "Windows":
        out = _run(["wmic", "cpu", "get", "Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed", "/format:csv"])
        for line in out.splitlines():
            if line and not line.startswith("Node"):
                parts = line.split(",")
                if len(parts) >= 5:
                    info.setdefault("freq_max_mhz", _safe_int(parts[1]))
                    info.setdefault("model", parts[3])
                    info.setdefault("cores_physical", _safe_int(parts[2]))
                    info.setdefault("cores_logical", _safe_int(parts[4]))
                    break

    # macOS
    elif platform.system() == "Darwin":
        brand = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
        if brand:
            info["model"] = brand

    return info


# ------------------------------------------------------------------ #
# RAM
# ------------------------------------------------------------------ #

def _scan_memory() -> dict[str, Any]:
    info: dict[str, Any] = {}
    try:
        import psutil
        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()
        info["total_gb"] = round(vm.total / 1024**3, 1)
        info["swap_total_gb"] = round(sw.total / 1024**3, 1)
    except Exception:
        # /proc/meminfo fallback
        try:
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    info["total_gb"] = round(kb / 1024 / 1024, 1)
                elif line.startswith("SwapTotal:"):
                    kb = int(line.split()[1])
                    info["swap_total_gb"] = round(kb / 1024 / 1024, 1)
        except Exception:
            pass

    # Linux: DIMM bilgisi (dmidecode — root gerekebilir)
    if platform.system() == "Linux":
        out = _run(["dmidecode", "-t", "memory"], timeout=5)
        dimms: list[str] = []
        current: dict[str, str] = {}
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("Memory Device"):
                if current.get("Size") and current["Size"] != "No Module Installed":
                    dimms.append(f"{current.get('Size','?')} {current.get('Type','?')} {current.get('Speed','')}")
                current = {}
            for field in ("Size", "Type", "Speed", "Manufacturer", "Part Number"):
                if line.startswith(f"{field}:"):
                    current[field] = line.split(":", 1)[1].strip()
        if current.get("Size") and current["Size"] != "No Module Installed":
            dimms.append(f"{current.get('Size','?')} {current.get('Type','?')} {current.get('Speed','')}")
        if dimms:
            info["dimms"] = dimms
    return info


# ------------------------------------------------------------------ #
# GPU
# ------------------------------------------------------------------ #

def _scan_gpu() -> list[dict[str, Any]]:
    gpus: list[dict[str, Any]] = []

    # NVIDIA: nvidia-smi
    if shutil.which("nvidia-smi"):
        out = _run([
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ])
        for line in out.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                gpus.append({
                    "vendor": "NVIDIA",
                    "name": parts[0],
                    "vram_mb": _safe_int(parts[1]),
                    "driver": parts[2],
                })
        # CUDA versiyonu
        if gpus:
            cuda = _run(["nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader"])
            if cuda:
                for g in gpus:
                    g["cuda_compute"] = cuda.split("\n")[0].strip()

    # AMD / Intel: lspci (Linux)
    if platform.system() == "Linux" and shutil.which("lspci"):
        out = _run(["lspci", "-mm"])
        for line in out.splitlines():
            low = line.lower()
            if "vga" in low or "3d" in low or "display" in low:
                # lspci -mm formatı: slot "class" "vendor" "device" ...
                parts = line.split('"')
                if len(parts) >= 7:
                    vendor = parts[3]
                    device = parts[5]
                    # NVIDIA zaten eklendi, tekrar ekleme
                    if "NVIDIA" in vendor and any(g.get("vendor") == "NVIDIA" for g in gpus):
                        continue
                    gpus.append({"vendor": vendor, "name": device})

    # macOS: system_profiler
    if platform.system() == "Darwin":
        out = _run(["system_profiler", "SPDisplaysDataType", "-json"], timeout=15)
        try:
            data = json.loads(out)
            for d in data.get("SPDisplaysDataType", []):
                gpus.append({
                    "name": d.get("spdisplays_device-id", d.get("sppci_model", "?")),
                    "vram_mb": d.get("spdisplays_vram", "?"),
                    "vendor": d.get("spdisplays_vendor", "?"),
                })
        except Exception:
            pass

    # Windows: WMIC
    if platform.system() == "Windows" and not gpus:
        out = _run(["wmic", "path", "win32_VideoController", "get",
                    "Name,AdapterRAM,DriverVersion", "/format:csv"])
        for line in out.splitlines():
            if line and not line.startswith("Node"):
                parts = line.split(",")
                if len(parts) >= 4 and parts[2]:
                    vram = _safe_int(parts[1])
                    gpus.append({
                        "name": parts[2],
                        "vram_mb": vram // (1024 * 1024) if vram else 0,
                        "driver": parts[3] if len(parts) > 3 else "",
                    })
    return gpus


# ------------------------------------------------------------------ #
# Depolama
# ------------------------------------------------------------------ #

def _scan_storage() -> list[dict[str, Any]]:
    disks: list[dict[str, Any]] = []

    # psutil: mount noktaları ve boyutlar
    try:
        import psutil
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append({
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype,
                    "total_gb": round(usage.total / 1024**3, 1),
                    "free_gb": round(usage.free / 1024**3, 1),
                })
            except Exception:
                pass
    except Exception:
        pass

    # Linux: lsblk ile disk modeli ve tipi
    if platform.system() == "Linux" and shutil.which("lsblk"):
        out = _run(["lsblk", "-o", "NAME,MODEL,SIZE,TYPE,ROTA,TRAN", "--json"])
        try:
            data = json.loads(out)
            for bd in data.get("blockdevices", []):
                if bd.get("type") not in ("disk", "loop"):
                    continue
                model = (bd.get("model") or "").strip()
                rota = bd.get("rota", "1")
                tran = bd.get("tran", "")
                disk_type = "HDD" if str(rota) == "1" else "SSD"
                if tran in ("nvme",):
                    disk_type = "NVMe SSD"
                # Mount noktası üzerindeki diskleri güncelle
                dev_name = f"/dev/{bd['name']}"
                for d in disks:
                    if d["device"].startswith(dev_name):
                        if model:
                            d["model"] = model
                        d["type"] = disk_type
                # Eğer hiç mount noktası yoksa yine de ekle
                if not any(d["device"].startswith(dev_name) for d in disks):
                    disks.append({
                        "device": dev_name,
                        "model": model,
                        "size": bd.get("size", "?"),
                        "type": disk_type,
                    })
        except Exception:
            pass

    return disks


# ------------------------------------------------------------------ #
# Ağ adaptörleri
# ------------------------------------------------------------------ #

def _scan_network() -> list[dict[str, Any]]:
    adapters: list[dict[str, Any]] = []
    try:
        import psutil
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
        for name, st in stats.items():
            if name in ("lo", "Loopback Pseudo-Interface 1"):
                continue
            entry: dict[str, Any] = {
                "name": name,
                "is_up": st.isup,
                "speed_mbps": st.speed if st.speed > 0 else None,
            }
            # MAC adresi
            import socket
            for addr in addrs.get(name, []):
                if addr.family == psutil.AF_LINK:  # type: ignore
                    entry["mac"] = addr.address
                elif addr.family == socket.AF_INET:
                    entry["ipv4"] = addr.address
            # Kablosuz mu kablolu mu?
            if platform.system() == "Linux":
                wireless_path = Path(f"/sys/class/net/{name}/wireless")
                entry["type"] = "wifi" if wireless_path.exists() else "ethernet"
            adapters.append(entry)
    except Exception:
        pass
    return adapters


# ------------------------------------------------------------------ #
# USB cihazlar
# ------------------------------------------------------------------ #

def _scan_usb() -> list[str]:
    devices: list[str] = []
    if platform.system() == "Linux" and shutil.which("lsusb"):
        out = _run(["lsusb"])
        for line in out.splitlines():
            # "Bus 001 Device 002: ID 046d:c52b Logitech..."
            if ":" in line:
                desc = line.split(":", 1)[-1].strip()
                if desc and "hub" not in desc.lower():
                    devices.append(desc)
    elif platform.system() == "Windows":
        out = _run(["wmic", "path", "Win32_USBHub", "get", "Description", "/format:csv"])
        for line in out.splitlines():
            if line and not line.startswith("Node") and "," in line:
                devices.append(line.split(",", 1)[-1].strip())
    return devices[:20]  # En fazla 20 cihaz


# ------------------------------------------------------------------ #
# Değişiklik tespiti
# ------------------------------------------------------------------ #

_TRACKED_FIELDS = {
    "os.distro", "os.kernel", "os.release",
    "cpu.model", "cpu.cores_physical", "cpu.cores_logical",
    "memory.total_gb", "memory.swap_total_gb",
}


def _flatten(d: dict, prefix: str = "") -> dict[str, Any]:
    """Nested dict'i düz key-value çiftlerine dönüştürür."""
    result: dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            result.update(_flatten(v, key))
        else:
            result[key] = v
    return result


def _detect_changes(old: dict, new: dict) -> list[dict]:
    changes: list[dict] = []
    old_flat = _flatten(old)
    new_flat = _flatten(new)
    now = dt.datetime.now(dt.timezone.utc).isoformat()

    for field in _TRACKED_FIELDS:
        old_val = old_flat.get(field)
        new_val = new_flat.get(field)
        if old_val is None and new_val is None:
            continue
        if old_val != new_val:
            changes.append({
                "detected_at": now,
                "field": field,
                "old": old_val,
                "new": new_val,
            })

    # Yeni GPU eklendi mi / çıkarıldı mı?
    old_gpus = {g.get("name", "") for g in old.get("gpu", [])}
    new_gpus = {g.get("name", "") for g in new.get("gpu", [])}
    for added in new_gpus - old_gpus:
        changes.append({"detected_at": now, "field": "gpu.added", "old": None, "new": added})
    for removed in old_gpus - new_gpus:
        changes.append({"detected_at": now, "field": "gpu.removed", "old": removed, "new": None})

    # Yeni disk eklendi mi?
    old_devs = {d.get("device", "") for d in old.get("storage", [])}
    new_devs = {d.get("device", "") for d in new.get("storage", [])}
    for added in new_devs - old_devs:
        changes.append({"detected_at": now, "field": "storage.added", "old": None, "new": added})
    for removed in old_devs - new_devs:
        changes.append({"detected_at": now, "field": "storage.removed", "old": removed, "new": None})

    return changes


def _save_changes(new_changes: list[dict]) -> None:
    if not new_changes:
        return
    cf = _changes_file()
    existing: list[dict] = []
    if cf.exists():
        try:
            existing = json.loads(cf.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    combined = (new_changes + existing)[:200]  # Son 200 değişiklik
    cf.write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")


# ------------------------------------------------------------------ #
# Ana tarama fonksiyonu
# ------------------------------------------------------------------ #

def _safe_int(val: Any) -> int:
    try:
        return int(val)
    except Exception:
        return 0


def scan_hardware(notify_changes: bool = True) -> dict[str, Any]:
    """
    Tam donanım taraması yapar. Sonucu dosyaya yazar.
    Değişiklik varsa bildirim gönderir.
    """
    prev: dict[str, Any] = {}
    pf = _profile_file()
    if pf.exists():
        try:
            prev = json.loads(pf.read_text(encoding="utf-8"))
        except Exception:
            prev = {}

    profile: dict[str, Any] = {
        "scanned_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "platform": platform.system(),
        "os": _scan_os(),
        "cpu": _scan_cpu(),
        "memory": _scan_memory(),
        "gpu": _scan_gpu(),
        "storage": _scan_storage(),
        "network": _scan_network(),
        "usb": _scan_usb(),
    }

    # Değişiklik tespiti
    if prev:
        changes = _detect_changes(prev, profile)
        profile["previous_scan_at"] = prev.get("scanned_at")
        if changes:
            _save_changes(changes)
            if notify_changes:
                change_summary = "; ".join(
                    f"{c['field']}: {c['old']} → {c['new']}" for c in changes[:3]
                )
                _notify(
                    title="Donanım değişikliği tespit edildi",
                    message=change_summary,
                    kind="info",
                )
    else:
        profile["previous_scan_at"] = None

    pf.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return profile


# ------------------------------------------------------------------ #
# Okuma / özet
# ------------------------------------------------------------------ #

def get_hardware_profile() -> dict[str, Any]:
    """Kaydedilmiş profili döner. Yoksa tarama yapar."""
    pf = _profile_file()
    if pf.exists():
        try:
            return json.loads(pf.read_text(encoding="utf-8"))
        except Exception:
            pass
    return scan_hardware(notify_changes=False)


def hardware_summary_short() -> str:
    """
    Sistem promptuna eklenecek kısa donanım özeti.
    Nasri'nin ne üzerinde çalıştığını bilmesi için.
    """
    try:
        p = get_hardware_profile()
    except Exception:
        return ""

    parts: list[str] = []

    cpu = p.get("cpu", {})
    if cpu.get("model"):
        cores = cpu.get("cores_logical", "?")
        parts.append(f"CPU: {cpu['model']} ({cores} iş parçacığı)")

    mem = p.get("memory", {})
    if mem.get("total_gb"):
        parts.append(f"RAM: {mem['total_gb']} GB")

    gpus = p.get("gpu", [])
    for g in gpus[:2]:
        name = g.get("name", "")
        vram = g.get("vram_mb")
        vram_str = f" {vram // 1024} GB VRAM" if vram else ""
        if name:
            parts.append(f"GPU: {name}{vram_str}")

    os_info = p.get("os", {})
    os_str = os_info.get("distro") or f"{os_info.get('system', '')} {os_info.get('release', '')}".strip()
    if os_str:
        parts.append(f"OS: {os_str}")

    storage = p.get("storage", [])
    total_storage = sum(d.get("total_gb", 0) for d in storage if d.get("total_gb"))
    if total_storage:
        parts.append(f"Depolama: {round(total_storage, 0):.0f} GB toplam")

    if not parts:
        return ""
    return "Donanım: " + " | ".join(parts)


def get_hardware_changes() -> list[dict]:
    """Son tespit edilen donanım değişikliklerini döner."""
    cf = _changes_file()
    if not cf.exists():
        return []
    try:
        return json.loads(cf.read_text(encoding="utf-8"))
    except Exception:
        return []


def should_rescan(interval_hours: int = 24) -> bool:
    """Son taramadan bu yana yeterli süre geçti mi?"""
    pf = _profile_file()
    if not pf.exists():
        return True
    try:
        data = json.loads(pf.read_text(encoding="utf-8"))
        last = dt.datetime.fromisoformat(data["scanned_at"])
        return (dt.datetime.now(dt.timezone.utc) - last) >= dt.timedelta(hours=interval_hours)
    except Exception:
        return True
