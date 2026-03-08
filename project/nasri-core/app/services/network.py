from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import os
import re
import subprocess
from typing import Any

from app.core.settings import get_settings

_NMAP_UP_LINE = re.compile(r"^Host:\s+(\S+)\s+\((.*?)\)\s+Status:\s+Up$", re.IGNORECASE)
_NMAP_UP_NOHOST = re.compile(r"^Host:\s+(\S+)\s+Status:\s+Up$", re.IGNORECASE)


class NetworkDiscoveryError(Exception):
    pass


@dataclass
class DiscoveredDevice:
    ip: str
    hostname: str | None
    source: str
    ownership_score: int
    ownership_label: str


def _normalize_cidr(target_cidr: str) -> str:
    try:
        network = ipaddress.ip_network(target_cidr, strict=False)
    except ValueError as exc:
        raise NetworkDiscoveryError("Geçersiz target_cidr.") from exc
    return str(network)


def _score_ownership(hostname: str | None) -> tuple[int, str]:
    if not hostname:
        return 20, "unknown"
    host = hostname.lower()
    local_user = os.getenv("USERNAME", "").lower()
    local_host = os.getenv("COMPUTERNAME", "").lower()
    score = 20
    if any(k in host for k in ("nasri", "home", "local", "desktop", "laptop")):
        score += 30
    if local_user and local_user in host:
        score += 30
    if local_host and local_host in host:
        score += 30
    if score >= 80:
        return score, "likely_owned"
    if score >= 50:
        return score, "possible_owned"
    return score, "unknown"


def _parse_nmap_grepable(output: str) -> list[tuple[str, str | None]]:
    devices: list[tuple[str, str | None]] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or "Status: Up" not in line:
            continue
        m = _NMAP_UP_LINE.match(line)
        if m:
            ip = m.group(1).strip()
            host = m.group(2).strip() or None
            if host == "":
                host = None
            devices.append((ip, host))
            continue
        m2 = _NMAP_UP_NOHOST.match(line)
        if m2:
            devices.append((m2.group(1).strip(), None))
    return devices


def _scan_with_nmap(target_cidr: str) -> list[tuple[str, str | None]]:
    s = get_settings()
    cmd = ["nmap", "-sn", target_cidr, "-oG", "-"]
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=s.lan_scan_timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise NetworkDiscoveryError("nmap bulunamadı. Lütfen nmap kurun.") from exc
    except subprocess.TimeoutExpired as exc:
        raise NetworkDiscoveryError("nmap taraması zaman aşımına uğradı.") from exc

    if proc.returncode != 0:
        detail = proc.stderr.strip() or "nmap başarısız döndü."
        raise NetworkDiscoveryError(detail)
    return _parse_nmap_grepable(proc.stdout)


def _scan_mdns() -> list[tuple[str, str | None]]:
    try:
        from zeroconf import Zeroconf
        from zeroconf import ServiceBrowser
        from zeroconf import ServiceListener
    except Exception:
        return []

    found: list[tuple[str, str | None]] = []

    class _Listener(ServiceListener):
        def add_service(self, zc: Any, type_: str, name: str) -> None:
            info = zc.get_service_info(type_, name, timeout=500)
            if not info:
                return
            host = info.server.rstrip(".") if info.server else None
            for addr in info.parsed_addresses():
                found.append((addr, host))

        def update_service(self, zc: Any, type_: str, name: str) -> None:
            self.add_service(zc, type_, name)

        def remove_service(self, zc: Any, type_: str, name: str) -> None:
            return

    zc = Zeroconf()
    try:
        _ = ServiceBrowser(zc, "_services._dns-sd._udp.local.", _Listener())
        import time

        time.sleep(1.2)
    finally:
        zc.close()
    return found


def discover_devices(
    *,
    target_cidr: str | None = None,
    include_mdns: bool = True,
) -> list[DiscoveredDevice]:
    s = get_settings()
    cidr = _normalize_cidr(target_cidr or s.lan_scan_default_cidr)
    raw: dict[str, DiscoveredDevice] = {}

    for ip, host in _scan_with_nmap(cidr):
        score, label = _score_ownership(host)
        raw[ip] = DiscoveredDevice(
            ip=ip,
            hostname=host,
            source="nmap",
            ownership_score=score,
            ownership_label=label,
        )

    if include_mdns and s.lan_scan_mdns_enabled:
        for ip, host in _scan_mdns():
            score, label = _score_ownership(host)
            if ip in raw:
                if raw[ip].hostname is None and host:
                    raw[ip].hostname = host
                if raw[ip].source != "nmap+mdns":
                    raw[ip].source = "nmap+mdns"
                raw[ip].ownership_score = max(raw[ip].ownership_score, score)
                raw[ip].ownership_label = label
                continue
            raw[ip] = DiscoveredDevice(
                ip=ip,
                hostname=host,
                source="mdns",
                ownership_score=score,
                ownership_label=label,
            )

    return sorted(raw.values(), key=lambda x: (-x.ownership_score, x.ip))
