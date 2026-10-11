from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from hjemmefra.api.deps import get_session, require_household
from hjemmefra.api.schemas import PlanCreate
from hjemmefra.core.errors import NotFound
from hjemmefra.core.money import Money
from hjemmefra.domain.household import Household
from hjemmefra.domain.plan import ObjectiveWeights, OptimizationMode, PlanRequest, PlanResult
from hjemmefra.optimization.weights import weights_for
from hjemmefra.persistence.repositories import OfferRepo, PantryRepo, PlanRepo, ProductRepo, RecipeRepo, StoreRepo
from hjemmefra.planning.service import PlanningData, generate_plan

router = APIRouter(tags=["plans"])


@router.post("/households/{household_id}/plans", response_model=PlanResult, status_code=201)
def create_plan(household_id: str, body: PlanCreate, hh: Household = Depends(require_household), s: Session = Depends(get_session)):
    plans = PlanRepo(s)
    if body.idempotency_key:
        existing = plans.by_idempotency(household_id, body.idempotency_key)
        if existing:
            return existing
    pantry = PantryRepo(s)
    pantry_version = pantry.version(household_id)
    offers_repo = OfferRepo(s)
    req = PlanRequest(household_id=household_id, start_date=body.start_date, days=body.days, shopping_dates=body.shopping_dates,
                      servings_per_meal=body.servings_per_meal,
                      budget_minor=Money.from_decimal(body.budget_dkk).minor if body.budget_dkk is not None else None,
                      budget_mode=body.budget_mode, optimization_modes=body.optimization_modes, custom_weights=body.custom_weights,
                      max_stores=body.max_stores, max_distance_km=body.max_distance_km, max_prep_minutes=body.max_prep_minutes,
                      selected_store_ids=body.selected_store_ids, pantry_version=body.pantry_version,
                      allow_leftover_meals=body.allow_leftover_meals, time_limit_seconds=body.time_limit_seconds)
    shopping = req.shopping_dates or [req.start_date]
    offers = []
    seen = set()
    for d in shopping:
        for o in offers_repo.valid_on(d):
            if o.offer_id not in seen:
                seen.add(o.offer_id)
                offers.append(o)
    data = PlanningData(household=hh, stores=StoreRepo(s).all(), offers=offers,
                        products={p.canonical_id: p for p in ProductRepo(s).all()}, recipes=RecipeRepo(s).all(),
                        pantry_lots=pantry.lots(household_id), pantry_version=pantry_version, history=offers_repo.observations())
    result = generate_plan(req, data, now=datetime.now(timezone.utc))
    plans.save(result, body.idempotency_key)
    return result


@router.get("/households/{household_id}/plans", response_model=List[PlanResult])
def list_plans(household_id: str, hh: Household = Depends(require_household), s: Session = Depends(get_session)):
    return PlanRepo(s).list_for(household_id)


@router.get("/households/{household_id}/plans/{plan_id}", response_model=PlanResult)
def get_plan(household_id: str, plan_id: str, hh: Household = Depends(require_household), s: Session = Depends(get_session)):
    try:
        plan = PlanRepo(s).get(plan_id)
    except NotFound:
        raise HTTPException(404, "plan not found")
    if plan.household_id != household_id:
        raise HTTPException(403, "forbidden")
    return plan


@router.get("/households/{household_id}/plans/{plan_id}/shopping-list")
def shopping_list(household_id: str, plan_id: str, scenario: OptimizationMode = OptimizationMode.BALANCED,
                  hh: Household = Depends(require_household), s: Session = Depends(get_session)):
    plan = get_plan(household_id, plan_id, hh, s)
    sc = next((x for x in plan.scenarios if x.mode == scenario and not x.relaxed_constraints), None)
    if sc is None:
        raise HTTPException(404, "scenario not in plan")
    return {"plan_id": plan_id, "scenario": scenario, "status": sc.status, "stores": sc.store_breakdown,
            "checkout_total_minor": sc.checkout_total_minor, "deposit_total_minor": sc.deposit_total_minor,
            "pantry_uses": sc.pantry_uses, "confidence": sc.confidence, "warnings": sc.warnings}


@router.get("/optimization/modes", tags=["optimization"])
def optimization_modes():
    """Documented modes and their default weights."""
    from datetime import date
    dummy = PlanRequest(household_id="x", start_date=date.today(), days=1)
    return {m.value: {"weights": weights_for(m, dummy)[0], "overrides": {k: (v.value if hasattr(v, "value") else v) for k, v in weights_for(m, dummy)[1].items()}}
            for m in OptimizationMode}


@router.get("/optimization/default-weights", response_model=ObjectiveWeights, tags=["optimization"])
def default_weights():
    return ObjectiveWeights()
