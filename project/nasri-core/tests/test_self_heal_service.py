from __future__ import annotations

import pytest

import app.services.self_heal as sh_module


class _Settings:
    self_heal_enabled = True
    self_heal_auto_fix = False
    self_heal_anomaly_limit = 20


@pytest.mark.asyncio
async def test_self_heal_plan_only(monkeypatch):
    monkeypatch.setattr(sh_module, "get_settings", lambda: _Settings())
    monkeypatch.setattr(
        sh_module,
        "get_maintenance_status",
        lambda: __import__("asyncio").sleep(0, result={"due": True, "last_result": "ok"}),
    )
    monkeypatch.setattr(
        sh_module,
        "list_alerts",
        lambda limit=20: __import__("asyncio").sleep(
            0, result=[{"severity": "high"}]
        ),
    )

    issues, actions, healed = await sh_module.run_self_heal(force=False)
    assert len(issues) >= 1
    assert actions[0].action == "plan_only"
    assert healed is False


@pytest.mark.asyncio
async def test_self_heal_force_executes(monkeypatch):
    monkeypatch.setattr(sh_module, "get_settings", lambda: _Settings())
    monkeypatch.setattr(
        sh_module,
        "get_maintenance_status",
        lambda: __import__("asyncio").sleep(0, result={"due": True, "last_result": "failed"}),
    )
    monkeypatch.setattr(
        sh_module,
        "list_alerts",
        lambda limit=20: __import__("asyncio").sleep(
            0, result=[{"severity": "high"}]
        ),
    )
    monkeypatch.setattr(
        sh_module,
        "run_maintenance",
        lambda trigger="self-heal": __import__("asyncio").sleep(0, result={"ok": True}),
    )
    monkeypatch.setattr(
        sh_module,
        "run_backup",
        lambda trigger="self-heal": __import__("asyncio").sleep(0, result={"backup_id": "b1"}),
    )

    issues, actions, healed = await sh_module.run_self_heal(force=True)
    assert len(issues) >= 1
    assert any(a.action == "maintenance.run" and a.executed for a in actions)
    assert healed is True
