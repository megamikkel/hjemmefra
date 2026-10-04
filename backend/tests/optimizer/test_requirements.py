"""Recipe-level ingredient requirements must hold regardless of recipe order (regression)."""
from hjemmefra.domain.plan import OptimizationMode, PlanStatus
from hjemmefra.planning.service import generate_plan
from tests.conftest import make_request


def _bolognese_lines(plan):
    for s in plan.scenarios:
        if s.status != PlanStatus.OK:
            continue
        has_bolo = any(m.recipe_id == "spaghetti_bolognese" for m in s.meals)
        has_chili = any(m.recipe_id == "chili_con_carne" for m in s.meals)
        yield s, has_bolo, has_chili


def test_fat_limit_respected_for_any_recipe_order(demo_data):
    data, _ = demo_data
    for order in (list(data.recipes), sorted(data.recipes, key=lambda r: r.recipe_id), sorted(data.recipes, key=lambda r: r.recipe_id, reverse=True)):
        d2 = data.__class__(**{**data.__dict__, "recipes": order})
        plan = generate_plan(make_request(optimization_modes=[OptimizationMode.CHEAPEST, OptimizationMode.ONE_STORE]), d2)
        for s, has_bolo, has_chili in _bolognese_lines(plan):
            beef = {p.canonical_product_id for p in s.purchases if p.canonical_product_id.startswith("BEEF")}
            if has_bolo and not has_chili:
                assert "BEEF_MINCED_14_18" not in beef
            if has_bolo and has_chili and "BEEF_MINCED_14_18" in beef:
                # 14-18 may only cover chili demand; bolognese demand must be covered by 8-12
                assert "BEEF_MINCED_8_12" in beef
            # totals identical across orders
        totals = [s.checkout_total_minor for s in plan.scenarios]
        assert totals == [20300, 26900], totals
