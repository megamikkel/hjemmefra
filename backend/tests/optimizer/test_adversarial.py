"""Adversarial / edge cases (requirement 55)."""
from datetime import date, timedelta
from decimal import Decimal

from hjemmefra.core.confidence import Confidence
from hjemmefra.demo.dataset import HOUSEHOLD
from hjemmefra.domain.household import Allergen, Membership
from hjemmefra.domain.plan import BudgetMode, OptimizationMode, OptimizationStatus, PlanStatus
from hjemmefra.planning.service import generate_plan
from tests.conftest import make_request


def run(data, **kw):
    return generate_plan(make_request(**kw), data)


def test_budget_infeasible_returns_no_feasible_plan_with_minimum_and_next_best(demo_data):
    data, _ = demo_data
    plan = run(data, budget_minor=5000, budget_mode=BudgetMode.HARD, optimization_modes=[OptimizationMode.BUDGET], days=3)
    infeasible = plan.scenarios[0]
    assert infeasible.status == PlanStatus.NO_FEASIBLE_PLAN
    assert infeasible.minimum_estimated_required_budget_minor is not None and infeasible.minimum_estimated_required_budget_minor > 5000
    assert "BUDGET_INFEASIBLE" in infeasible.infeasibility_reason
    assert len(plan.scenarios) == 2 and plan.scenarios[1].relaxed_constraints == ["BUDGET"]
    assert plan.scenarios[1].checkout_total_minor >= infeasible.minimum_estimated_required_budget_minor > 5000


def test_hard_budget_never_exceeded(demo_data):
    data, _ = demo_data
    plan = run(data, budget_minor=15000, budget_mode=BudgetMode.HARD, optimization_modes=[OptimizationMode.BUDGET], days=3)
    sc = plan.scenarios[0]
    assert sc.status == PlanStatus.OK and sc.checkout_total_minor <= 15000


def test_membership_unlocks_member_offer(demo_data):
    data, _ = demo_data
    data2 = data.__class__(**{**data.__dict__})
    data2.household = HOUSEHOLD.model_copy(deep=True)
    data2.household.memberships = [Membership(program_id="lidl_plus")]
    plan = run(data2, optimization_modes=[OptimizationMode.CHEAPEST], days=7)
    assert not any("frikadeller" in w for w in plan.coverage_warnings)


def test_allergen_is_hard_constraint(demo_data):
    data, _ = demo_data
    data2 = data.__class__(**{**data.__dict__})
    data2.household = HOUSEHOLD.model_copy(deep=True)
    data2.household.preferences.allergens = [Allergen.GLUTEN, Allergen.EGG]
    plan = run(data2, optimization_modes=[OptimizationMode.CHEAPEST], days=4)
    sc = plan.scenarios[0]
    assert sc.status == PlanStatus.OK
    assert all(p.canonical_product_id not in ("PASTA", "TORTILLA", "EGGS") for p in sc.purchases)
    assert all(m.recipe_id not in ("spaghetti_bolognese", "tacos_okse", "omelet", "kartoffel_omelet", "pasta_broccoli") for m in sc.meals)


def test_expired_offers_are_not_used_on_later_shopping_date(demo_data):
    data, _ = demo_data
    plan = run(data, start_date=date(2026, 10, 12), shopping_dates=[date(2026, 10, 12)], optimization_modes=[OptimizationMode.CHEAPEST], days=3)
    assert plan.scenarios[0].status == PlanStatus.NO_FEASIBLE_PLAN
    assert plan.scenarios[0].purchases == []


def test_store_specific_offer_only_at_its_store(demo_data):
    data, _ = demo_data
    plan = run(data, optimization_modes=[OptimizationMode.CHEAPEST, OptimizationMode.BALANCED, OptimizationMode.ONE_STORE], days=7)
    offer = next(o for o in data.offers if o.raw_title.startswith("Kyllingebryst 600 g"))
    for s in plan.scenarios:
        for p in s.purchases:
            if p.offer_id == offer.offer_id:
                assert p.store_id == "netto_risskov"


def test_low_confidence_ocr_salmon_never_in_cheapest(demo_data):
    data, _ = demo_data
    ocr = next(o for o in data.offers if o.price_confidence == Confidence.LOW)
    plan = run(data, optimization_modes=[OptimizationMode.CHEAPEST, OptimizationMode.BALANCED], days=7)
    for s in plan.scenarios:
        assert all(p.offer_id != ocr.offer_id for p in s.purchases)


def test_third_store_only_if_it_pays_after_penalty(demo_data):
    data, _ = demo_data
    plan = run(data, optimization_modes=[OptimizationMode.BALANCED], days=7, max_stores=3)
    sc = plan.scenarios[0]
    # BALANCED accepts an extra store only when it saves more than store penalty + travel; golden shows 2 stores
    assert sc.store_count == 2


def test_timeout_returns_feasible_not_optimal_label(demo_data):
    data, _ = demo_data
    plan = run(data, optimization_modes=[OptimizationMode.BALANCED], days=7, time_limit_seconds=0.5)
    sc = plan.scenarios[0]
    assert sc.optimization_status in (OptimizationStatus.OPTIMAL, OptimizationStatus.FEASIBLE, OptimizationStatus.TIME_LIMIT)
    if sc.optimization_status != OptimizationStatus.OPTIMAL:
        assert any("ikke bevist optimal" in w for w in sc.warnings)


def test_no_stores_in_range(demo_data):
    data, _ = demo_data
    plan = run(data, max_distance_km=0.1, optimization_modes=[OptimizationMode.CHEAPEST], days=2)
    sc = plan.scenarios[0]
    assert sc.status == PlanStatus.NO_FEASIBLE_PLAN and "NO_" in sc.infeasibility_reason


def test_one_store_mode_uses_one_store(demo_data):
    data, _ = demo_data
    plan = run(data, optimization_modes=[OptimizationMode.ONE_STORE], days=5, max_stores=3)
    assert plan.scenarios[0].store_count == 1
