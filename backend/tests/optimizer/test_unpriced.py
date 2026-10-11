"""Ingredients without a known price: allowed only when safe, never counted, always listed."""
from decimal import Decimal

from hjemmefra.core.units import Unit
from hjemmefra.domain.household import Allergen
from hjemmefra.domain.plan import OptimizationMode, PlanStatus
from hjemmefra.domain.recipe import RecipeIngredient
from hjemmefra.planning.service import generate_plan
from tests.conftest import make_request


def _with_unknown_ingredient(data, n_unknown=1):
    base = next(r for r in data.recipes if r.recipe_id == "spaghetti_bolognese")
    extra = [RecipeIngredient(canonical_ingredient_id=f"UNRESOLVED:x{i}", quantity=Decimal(1), unit=Unit.STK,
                              note=f"1 tsk hemmelig krydderi {i}", unpriced=True, optional=True) for i in range(n_unknown)]
    r = base.model_copy(update={"recipe_id": "bolo_x", "name": "Bolognese med ukendt", "review_required": True,
                                "ingredients": base.ingredients + extra})
    d2 = data.__class__(**{**data.__dict__, "recipes": [r]})
    return d2


def test_unpriced_recipe_rejected_by_default(demo_data):
    data, _ = demo_data
    plan = generate_plan(make_request(days=1, optimization_modes=[OptimizationMode.CHEAPEST]), _with_unknown_ingredient(data))
    assert plan.scenarios[0].status == PlanStatus.NO_FEASIBLE_PLAN


def test_unpriced_items_listed_and_excluded_from_total(demo_data):
    data, _ = demo_data
    plan = generate_plan(make_request(days=1, allow_unpriced_items=True, optimization_modes=[OptimizationMode.CHEAPEST]),
                         _with_unknown_ingredient(data))
    sc = plan.scenarios[0]
    assert sc.status == PlanStatus.OK and sc.meals[0].recipe_id == "bolo_x"
    assert [u["line"] for u in sc.unpriced_items] == ["1 tsk hemmelig krydderi 0"]
    assert sc.confidence.unknown_price_items == ["1 tsk hemmelig krydderi 0"] and sc.confidence.overall.value == "MEDIUM"
    assert sc.checkout_total_minor == sum(p.checkout_cost_minor for p in sc.purchases)
    assert any("uden kendt pris" in w for w in sc.warnings)


def test_unpriced_never_allowed_with_allergens_or_too_many(demo_data):
    data, _ = demo_data
    d = _with_unknown_ingredient(data)
    d.household = d.household.model_copy(deep=True)
    d.household.preferences.allergens = [Allergen.SESAME]
    plan = generate_plan(make_request(days=1, allow_unpriced_items=True, optimization_modes=[OptimizationMode.CHEAPEST]), d)
    assert plan.scenarios[0].status == PlanStatus.NO_FEASIBLE_PLAN
    plan = generate_plan(make_request(days=1, allow_unpriced_items=True, max_unpriced_per_recipe=2,
                                      optimization_modes=[OptimizationMode.CHEAPEST]), _with_unknown_ingredient(data, 3))
    assert plan.scenarios[0].status == PlanStatus.NO_FEASIBLE_PLAN


def test_unknown_major_ingredient_rejects_recipe(demo_data):
    data, _ = demo_data
    base = next(r for r in data.recipes if r.recipe_id == "spaghetti_bolognese")
    big = RecipeIngredient(canonical_ingredient_id="UNRESOLVED:meat", quantity=Decimal(500), unit=Unit.G,
                           note="500 g hakket hjortekød", unpriced=True, optional=True)
    r = base.model_copy(update={"recipe_id": "bolo_big", "review_required": True, "ingredients": base.ingredients + [big]})
    d = data.__class__(**{**data.__dict__, "recipes": [r]})
    plan = generate_plan(make_request(days=1, allow_unpriced_items=True, optimization_modes=[OptimizationMode.CHEAPEST]), d)
    sc = plan.scenarios[0]
    assert sc.status == PlanStatus.NO_FEASIBLE_PLAN and "UNKNOWN_MAJOR_INGREDIENT" in sc.infeasibility_reason
