from __future__ import annotations

import pytest

import app.services.home_automation as ha_module


class _Settings:
    home_assistant_enabled = False
    home_assistant_url = "http://localhost:8123"
    home_assistant_token = ""
    home_assistant_default_area = "salon"
    mqtt_enabled = True
    mqtt_host = "localhost"
    mqtt_port = 1883
    mqtt_username = ""
    mqtt_password = ""
    mqtt_topic_prefix = "nasri"


def test_detect_action_target():
    action, target = ha_module._detect_action_target("salondaki ışığı aç")
    assert action == "turn_on"
    assert target == "light"


@pytest.mark.asyncio
async def test_run_command_fallback_to_mqtt(monkeypatch):
    monkeypatch.setattr(ha_module, "get_settings", lambda: _Settings())

    async def _ha(*_args, **_kwargs):
        raise ha_module.HomeAutomationUnavailableError("kapali")

    calls = {"mqtt": 0}

    async def _mqtt(*_args, **_kwargs):
        calls["mqtt"] += 1

    monkeypatch.setattr(ha_module, "call_home_assistant", _ha)
    monkeypatch.setattr(ha_module, "publish_mqtt", _mqtt)

    mode_used, action, target = await ha_module.run_command(
        "salon ışığını kapat",
        mode="auto",
    )
    assert mode_used == "mqtt"
    assert action == "turn_off"
    assert target == "light"
    assert calls["mqtt"] == 1
