from __future__ import annotations

from dataclasses import dataclass
import os
import platform
import subprocess

from app.core.settings import get_settings


class DriverManagerError(Exception):
    pass


@dataclass
class DriverCandidate:
    device_id: str
    name: str
    status: str


def _run(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError:
        return 127, "", f"Komut bulunamadı: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", "Komut zaman aşımı."


def _scan_windows() -> list[DriverCandidate]:
    code, out, err = _run(["pnputil", "/enum-devices", "/problem"])
    if code != 0:
        raise DriverManagerError(err.strip() or "pnputil scan başarısız.")

    devices: list[DriverCandidate] = []
    current_id = ""
    current_name = ""
    for line in out.splitlines():
        row = line.strip()
        if row.lower().startswith("instance id:"):
            current_id = row.split(":", 1)[1].strip()
        elif row.lower().startswith("device description:"):
            current_name = row.split(":", 1)[1].strip()
        elif row.lower().startswith("problem code:"):
            problem = row.split(":", 1)[1].strip()
            if current_id:
                devices.append(
                    DriverCandidate(
                        device_id=current_id,
                        name=current_name or current_id,
                        status=f"problem:{problem}",
                    )
                )
                current_id = ""
                current_name = ""
    return devices


def _scan_linux() -> list[DriverCandidate]:
    code, out, err = _run(["ubuntu-drivers", "devices"])
    if code != 0:
        raise DriverManagerError(err.strip() or "ubuntu-drivers scan başarısız.")

    devices: list[DriverCandidate] = []
    current = ""
    for line in out.splitlines():
        row = line.strip()
        if row.startswith("==") and row.endswith("=="):
            current = row.strip("=").strip()
        elif "driver" in row and "recommended" in row:
            driver_name = row.split(":", 1)[0].strip()
            devices.append(
                DriverCandidate(
                    device_id=current or driver_name,
                    name=current or "unknown",
                    status=f"recommended:{driver_name}",
                )
            )
    return devices


def scan_missing_drivers() -> tuple[str, list[DriverCandidate]]:
    s = get_settings()
    if not s.driver_manager_enabled:
        raise DriverManagerError("Driver Manager devre dışı.")

    sys_name = platform.system().lower()
    if sys_name == "windows":
        return "windows", _scan_windows()
    if sys_name == "linux":
        return "linux", _scan_linux()
    raise DriverManagerError("Bu işletim sistemi desteklenmiyor.")


def _install_windows(device_id: str) -> tuple[bool, str]:
    code, out, err = _run(["pnputil", "/scan-devices"])
    if code != 0:
        return False, err.strip() or "pnputil /scan-devices başarısız."
    msg = out.strip() or "Sürücü taraması tamamlandı."
    return True, f"{device_id}: {msg}"


def _install_linux(device_id: str) -> tuple[bool, str]:
    env = os.environ.copy()
    env["DEBIAN_FRONTEND"] = "noninteractive"
    try:
        proc = subprocess.run(
            ["ubuntu-drivers", "autoinstall"],
            check=False,
            capture_output=True,
            text=True,
            timeout=900,
            env=env,
        )
    except FileNotFoundError:
        return False, "ubuntu-drivers komutu bulunamadı."
    except subprocess.TimeoutExpired:
        return False, "autoinstall zaman aşımı."
    if proc.returncode != 0:
        return False, proc.stderr.strip() or "autoinstall başarısız."
    return True, f"{device_id}: {proc.stdout.strip() or 'autoinstall tamamlandı'}"


def install_driver(device_id: str, auto_confirm: bool) -> tuple[bool, str]:
    s = get_settings()
    if not s.driver_manager_enabled:
        raise DriverManagerError("Driver Manager devre dışı.")
    if not auto_confirm and not s.driver_manager_auto_install:
        return False, "Kurulum dry-run modunda. auto_confirm=true ile tekrar deneyin."

    sys_name = platform.system().lower()
    if sys_name == "windows":
        return _install_windows(device_id)
    if sys_name == "linux":
        return _install_linux(device_id)
    raise DriverManagerError("Bu işletim sistemi desteklenmiyor.")
