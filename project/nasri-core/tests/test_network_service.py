from __future__ import annotations

import pytest

import app.services.network as network_module
from app.services.network import DiscoveredDevice, NetworkDiscoveryError


class _Settings:
    lan_scan_default_cidr = "192.168.1.0/24"
    lan_scan_timeout_seconds = 15
    lan_scan_mdns_enabled = True


def test_parse_nmap_grepable():
    out = """
Host: 192.168.1.10 (nasri-pi.local) Status: Up
Host: 192.168.1.12 () Status: Up
Host: 192.168.1.13 Status: Up
"""
    parsed = network_module._parse_nmap_grepable(out)
    assert parsed == [
        ("192.168.1.10", "nasri-pi.local"),
        ("192.168.1.12", None),
        ("192.168.1.13", None),
    ]


def test_discover_devices_merges_nmap_and_mdns(monkeypatch):
    monkeypatch.setattr(network_module, "get_settings", lambda: _Settings())
    monkeypatch.setattr(
        network_module,
        "_scan_with_nmap",
        lambda _cidr: [("192.168.1.10", "nasri-box"), ("192.168.1.20", None)],
    )
    monkeypatch.setattr(
        network_module,
        "_scan_mdns",
        lambda: [("192.168.1.20", "office-printer.local"), ("192.168.1.30", "tv.local")],
    )

    devices = network_module.discover_devices(target_cidr="192.168.1.0/24", include_mdns=True)
    by_ip = {d.ip: d for d in devices}

    assert isinstance(by_ip["192.168.1.10"], DiscoveredDevice)
    assert by_ip["192.168.1.20"].source == "nmap+mdns"
    assert by_ip["192.168.1.20"].hostname == "office-printer.local"
    assert by_ip["192.168.1.30"].source == "mdns"


def test_discover_devices_invalid_cidr():
    with pytest.raises(NetworkDiscoveryError, match="Geçersiz target_cidr"):
        network_module.discover_devices(target_cidr="not-a-cidr")
