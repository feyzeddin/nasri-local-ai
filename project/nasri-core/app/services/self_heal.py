from __future__ import annotations

from dataclasses import dataclass

from app.core.settings import get_settings
from app.services.anomaly import list_alerts
from app.services.backup import run_backup
from app.services.maintenance import get_maintenance_status, run_maintenance


class SelfHealError(Exception):
    pass


@dataclass
class HealAction:
    action: str
    executed: bool
    detail: str


def self_heal_status() -> dict:
    s = get_settings()
    return {
        "enabled": s.self_heal_enabled,
        "auto_fix": s.self_heal_auto_fix,
        "anomaly_limit": s.self_heal_anomaly_limit,
    }


async def _diagnose() -> list[str]:
    issues: list[str] = []
    m = await get_maintenance_status()
    if m.get("due"):
        issues.append("Maintenance due durumda.")
    if (m.get("last_result") or "").lower() == "failed":
        issues.append("Son maintenance sonucu failed.")

    alerts = await list_alerts(limit=get_settings().self_heal_anomaly_limit)
    high_alerts = [a for a in alerts if str(a.get("severity", "")).lower() == "high"]
    if high_alerts:
        issues.append(f"Yüksek seviye anomali sayısı: {len(high_alerts)}")
    return issues


async def run_self_heal(force: bool = False) -> tuple[list[str], list[HealAction], bool]:
    s = get_settings()
    if not s.self_heal_enabled:
        raise SelfHealError("Self-heal devre dışı.")

    issues = await _diagnose()
    actions: list[HealAction] = []
    if not issues:
        return [], [HealAction(action="noop", executed=False, detail="Sorun bulunmadı.")], True

    auto_fix = s.self_heal_auto_fix or force
    if not auto_fix:
        actions.append(
            HealAction(
                action="plan_only",
                executed=False,
                detail="Auto-fix kapalı. force=true ile onarım çalıştırılabilir.",
            )
        )
        return issues, actions, False

    # 1) bakım
    try:
        out = await run_maintenance(trigger="self-heal")
        actions.append(
            HealAction(
                action="maintenance.run",
                executed=True,
                detail=f"ok={out.get('ok')}",
            )
        )
    except Exception as exc:
        actions.append(
            HealAction(action="maintenance.run", executed=False, detail=str(exc))
        )

    # 2) güvenli yedek
    try:
        b = await run_backup(trigger="self-heal")
        actions.append(
            HealAction(
                action="backup.run",
                executed=True,
                detail=f"id={b.get('backup_id')}",
            )
        )
    except Exception as exc:
        actions.append(HealAction(action="backup.run", executed=False, detail=str(exc)))

    healed = any(a.executed for a in actions)
    return issues, actions, healed
