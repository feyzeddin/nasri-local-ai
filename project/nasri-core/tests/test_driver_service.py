from __future__ import annotations

import pytest

import app.services.driver as d_module


class _Settings:
    driver_manager_enabled = True
    driver_manager_auto_install = False


def test_scan_windows(monkeypatch):
    monkeypatch.setattr(d_module, "get_settings", lambda: _Settings())
    monkeypatch.setattr(d_module.platform, "system", lambda: "Windows")
    sample = """
Instance ID: PCI\\VEN_1234
Device Description: Test Device
Problem Code: 28
"""
    monkeypatch.setattr(d_module, "_run", lambda *_args, **_kwargs: (0, sample, ""))
    os_name, devices = d_module.scan_missing_drivers()
    assert os_name == "windows"
    assert len(devices) == 1


def test_install_dry_run(monkeypatch):
    monkeypatch.setattr(d_module, "get_settings", lambda: _Settings())
    ok, detail = d_module.install_driver("dev1", auto_confirm=False)
    assert ok is False
    assert "dry-run" in detail


def test_scan_unsupported_os(monkeypatch):
    monkeypatch.setattr(d_module, "get_settings", lambda: _Settings())
    monkeypatch.setattr(d_module.platform, "system", lambda: "Darwin")
    with pytest.raises(d_module.DriverManagerError, match="desteklenmiyor"):
        d_module.scan_missing_drivers()
