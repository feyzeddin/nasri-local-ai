from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PricingPlan(BaseModel):
    plan_id: str
    name: str
    monthly_price: float
    currency: str
    features: list[str]


class PricingPlanListResponse(BaseModel):
    count: int
    plans: list[PricingPlan]


class PricingQuoteRequest(BaseModel):
    plan_id: str = Field(min_length=1, max_length=32)
    seats: int = Field(default=1, ge=1, le=5000)
    billing_cycle: Literal["monthly", "yearly"] = "monthly"
    promo_code: str | None = Field(default=None, max_length=64)


class PricingQuoteResponse(BaseModel):
    plan_id: str
    seats: int
    billing_cycle: str
    currency: str
    base_amount: float
    discount_amount: float
    total_amount: float
    applied_discounts: list[str]


class PricingPromoValidationResponse(BaseModel):
    valid: bool
    code: str
    detail: str

