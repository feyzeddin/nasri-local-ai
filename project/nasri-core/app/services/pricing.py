from __future__ import annotations

from app.core.settings import get_settings


class PricingError(Exception):
    pass


def _plan_catalog() -> dict[str, dict]:
    currency = get_settings().pricing_currency
    return {
        "freemium": {
            "plan_id": "freemium",
            "name": "Freemium",
            "monthly_price": 0.0,
            "currency": currency,
            "features": ["Temel sohbet", "Sınırlı istek", "Topluluk desteği"],
        },
        "pro": {
            "plan_id": "pro",
            "name": "Pro",
            "monthly_price": 299.0,
            "currency": currency,
            "features": ["Gelişmiş otomasyon", "Öncelikli destek", "Beta özellikler"],
        },
        "enterprise": {
            "plan_id": "enterprise",
            "name": "Enterprise",
            "monthly_price": 1299.0,
            "currency": currency,
            "features": ["SSO/RBAC", "Kurumsal SLA", "Özel entegrasyonlar"],
        },
    }


def list_pricing_plans() -> list[dict]:
    plans = list(_plan_catalog().values())
    return sorted(plans, key=lambda x: x["monthly_price"])


def _early_access_codes() -> set[str]:
    raw = get_settings().pricing_early_access_codes
    return {x.strip().upper() for x in raw.split(",") if x.strip()}


def validate_promo_code(code: str) -> tuple[bool, str]:
    normalized = code.strip().upper()
    if not normalized:
        return False, "Kod boş."
    if normalized in _early_access_codes():
        return True, "Erken erişim indirimi uygulanabilir."
    return False, "Kod geçersiz."


def build_quote(
    *,
    plan_id: str,
    seats: int,
    billing_cycle: str,
    promo_code: str | None = None,
) -> dict:
    plans = _plan_catalog()
    plan = plans.get(plan_id.strip().lower())
    if plan is None:
        raise PricingError("Plan bulunamadı.")
    if seats <= 0:
        raise PricingError("seats pozitif olmalı.")
    cycle = billing_cycle.strip().lower()
    if cycle not in {"monthly", "yearly"}:
        raise PricingError("billing_cycle monthly veya yearly olmalı.")

    monthly_price = float(plan["monthly_price"])
    month_multiplier = 12 if cycle == "yearly" else 1
    base_amount = monthly_price * seats * month_multiplier
    discount_amount = 0.0
    applied: list[str] = []

    if cycle == "yearly" and base_amount > 0:
        rate = max(0, min(90, get_settings().pricing_annual_discount_percent))
        yearly_discount = base_amount * (rate / 100.0)
        discount_amount += yearly_discount
        applied.append(f"annual:{rate}%")

    code = (promo_code or "").strip()
    if code:
        valid, _ = validate_promo_code(code)
        if valid and base_amount > 0:
            rate = max(0, min(90, get_settings().pricing_early_access_extra_discount_percent))
            extra = base_amount * (rate / 100.0)
            discount_amount += extra
            applied.append(f"promo:{rate}%")

    total = max(0.0, base_amount - discount_amount)
    return {
        "plan_id": plan["plan_id"],
        "seats": seats,
        "billing_cycle": cycle,
        "currency": plan["currency"],
        "base_amount": round(base_amount, 2),
        "discount_amount": round(discount_amount, 2),
        "total_amount": round(total, 2),
        "applied_discounts": applied,
    }

