from __future__ import annotations

import app.services.pricing as pricing_module


class _Settings:
    pricing_currency = "TRY"
    pricing_annual_discount_percent = 20
    pricing_early_access_extra_discount_percent = 10
    pricing_early_access_codes = "NASRI2026,ERKEN2026"


def test_build_quote_yearly_with_promo(monkeypatch):
    monkeypatch.setattr(pricing_module, "get_settings", lambda: _Settings())
    out = pricing_module.build_quote(
        plan_id="pro",
        seats=2,
        billing_cycle="yearly",
        promo_code="NASRI2026",
    )
    assert out["plan_id"] == "pro"
    assert out["base_amount"] == 7176.0
    assert out["discount_amount"] == 2152.8
    assert out["total_amount"] == 5023.2
    assert "annual:20%" in out["applied_discounts"]
    assert "promo:10%" in out["applied_discounts"]


def test_validate_promo_code(monkeypatch):
    monkeypatch.setattr(pricing_module, "get_settings", lambda: _Settings())
    ok, _ = pricing_module.validate_promo_code("ERKEN2026")
    bad, _ = pricing_module.validate_promo_code("XXX")
    assert ok is True
    assert bad is False

