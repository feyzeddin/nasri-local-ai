from __future__ import annotations

import pytest

import app.services.zigbee as z_module


class _Settings:
    zigbee_enabled = True
    zigbee2mqtt_api_url = "http://localhost:8080"
    zigbee2mqtt_api_key = ""


@pytest.mark.asyncio
async def test_bridge_status(monkeypatch):
    monkeypatch.setattr(z_module, "get_settings", lambda: _Settings())

    async def _fake_request(_method: str, _path: str, payload=None):
        _ = payload
        return {"state": "online"}

    monkeypatch.setattr(z_module, "_request_json", _fake_request)
    online, detail = await z_module.bridge_status()
    assert online is True
    assert detail == "online"


@pytest.mark.asyncio
async def test_list_devices(monkeypatch):
    monkeypatch.setattr(z_module, "get_settings", lambda: _Settings())

    async def _fake_request(_method: str, _path: str, payload=None):
        _ = payload
        return [
            {
                "friendly_name": "kitchen_light",
                "ieee_address": "0x1",
                "definition": {"model": "M1", "vendor": "V1", "description": "D1"},
            }
        ]

    monkeypatch.setattr(z_module, "_request_json", _fake_request)
    items = await z_module.list_devices()
    assert len(items) == 1
    assert items[0]["friendly_name"] == "kitchen_light"


@pytest.mark.asyncio
async def test_permit_join(monkeypatch):
    monkeypatch.setattr(z_module, "get_settings", lambda: _Settings())

    async def _fake_request(_method: str, _path: str, payload=None):
        assert payload == {"value": 30}
        return {"ok": True}

    monkeypatch.setattr(z_module, "_request_json", _fake_request)
    accepted, detail = await z_module.permit_join(30)
    assert accepted is True
    assert "30" in detail
