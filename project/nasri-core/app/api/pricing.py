from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import AuthSession, require_roles
from app.schemas.pricing import (
    PricingPlan,
    PricingPlanListResponse,
    PricingPromoValidationResponse,
    PricingQuoteRequest,
    PricingQuoteResponse,
)
from app.services.pricing import (
    PricingError,
    build_quote,
    list_pricing_plans,
    validate_promo_code,
)

router = APIRouter(prefix="/pricing", tags=["pricing"])


@router.get("/plans", response_model=PricingPlanListResponse)
async def plans(
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> PricingPlanListResponse:
    rows = list_pricing_plans()
    return PricingPlanListResponse(count=len(rows), plans=[PricingPlan(**x) for x in rows])


@router.post("/quote", response_model=PricingQuoteResponse)
async def quote(
    body: PricingQuoteRequest,
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> PricingQuoteResponse:
    try:
        out = build_quote(
            plan_id=body.plan_id,
            seats=body.seats,
            billing_cycle=body.billing_cycle,
            promo_code=body.promo_code,
        )
    except PricingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PricingQuoteResponse(**out)


@router.get("/promo/{code}", response_model=PricingPromoValidationResponse)
async def promo(
    code: str,
    _session: AuthSession = Depends(require_roles("admin", "operator", "viewer")),
) -> PricingPromoValidationResponse:
    valid, detail = validate_promo_code(code)
    return PricingPromoValidationResponse(valid=valid, code=code, detail=detail)

