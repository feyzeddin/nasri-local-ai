"""
preflight.py — Nasri servis başlatmadan önce sağlık kontrolleri.

Her kontrol bir (ok: bool, name: str, detail: str) tuple döner.
run_preflight() genel bir özet döner ve başarısız kontrolleri raporlar.
"""
from __future__ import annotations

import importlib
import socket
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from typing import Callable

from .config import api_port


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


# ---------------------------------------------------------------------------
# Bireysel kontroller
# ---------------------------------------------------------------------------


def _check_python_version() -> CheckResult:
    ok = sys.version_info >= (3, 10)
    return CheckResult(
        name="Python >= 3.10",
        ok=ok,
        detail=f"mevcut: {sys.version.split()[0]}",
    )


def _check_module(module: str) -> CheckResult:
    try:
        importlib.import_module(module)
        return CheckResult(name=f"module:{module}", ok=True, detail="yüklü")
    except ImportError as exc:
        return CheckResult(name=f"module:{module}", ok=False, detail=str(exc))


def _check_redis() -> CheckResult:
    try:
        import redis as redis_lib  # noqa: PLC0415

        r = redis_lib.Redis(host="localhost", port=6379, socket_connect_timeout=2)
        r.ping()
        return CheckResult(name="Redis ping", ok=True, detail="pong")
    except Exception as exc:
        return CheckResult(name="Redis ping", ok=False, detail=str(exc))


def _check_ollama() -> CheckResult:
    try:
        url = "http://localhost:11434/api/tags"
        with urllib.request.urlopen(url, timeout=3):  # noqa: S310
            return CheckResult(name="Ollama API", ok=True, detail="erişilebilir")
    except Exception as exc:
        return CheckResult(name="Ollama API", ok=False, detail=str(exc))


def _check_port_free() -> CheckResult:
    port = api_port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", port))
            return CheckResult(name=f"Port {port} boş", ok=True, detail="kullanılabilir")
        except OSError:
            return CheckResult(
                name=f"Port {port} boş",
                ok=False,
                detail=f"port {port} zaten kullanımda",
            )


def _check_uvicorn_binary() -> CheckResult:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "uvicorn", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            ver = result.stdout.strip()
            return CheckResult(name="uvicorn", ok=True, detail=ver)
        return CheckResult(name="uvicorn", ok=False, detail=result.stderr.strip())
    except Exception as exc:
        return CheckResult(name="uvicorn", ok=False, detail=str(exc))


# ---------------------------------------------------------------------------
# Ana fonksiyon
# ---------------------------------------------------------------------------

# Zorunlu kontroller: başarısız olursa servis başlamaz
_REQUIRED: list[Callable[[], CheckResult]] = [
    _check_python_version,
    lambda: _check_module("fastapi"),
    lambda: _check_module("uvicorn"),
    lambda: _check_module("redis"),
    _check_uvicorn_binary,
    _check_port_free,
]

# İsteğe bağlı kontroller: başarısız olursa uyarı verilir, servis çalışmaya devam eder
_OPTIONAL: list[Callable[[], CheckResult]] = [
    _check_redis,
    _check_ollama,
    lambda: _check_module("chromadb"),
    lambda: _check_module("cryptography"),
]


def run_preflight(verbose: bool = True) -> tuple[bool, list[CheckResult]]:
    """
    Tüm kontrolleri çalıştırır.

    Dönüş:
        (all_required_ok, results_list)
    """
    results: list[CheckResult] = []
    all_ok = True

    for fn in _REQUIRED:
        r = fn()
        results.append(r)
        if verbose:
            icon = "✓" if r.ok else "✗"
            prefix = f"[{icon}]"
            print(f"  {prefix} {r.name}: {r.detail}")
        if not r.ok:
            all_ok = False

    for fn in _OPTIONAL:
        r = fn()
        results.append(r)
        if verbose:
            icon = "✓" if r.ok else "!"
            prefix = f"[{icon}]"
            print(f"  {prefix} {r.name}: {r.detail}")

    return all_ok, results
