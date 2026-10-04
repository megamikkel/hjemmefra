"""Golden cases on the demo dataset. Numbers are produced by the engine and pinned."""
from hjemmefra.domain.plan import OptimizationMode, OptimizationStatus, PlanStatus


def scenario(plan, mode):
    return next(s for s in plan.scenarios if s.mode == mode and not s.relaxed_constraints)


def test_golden_totals(golden_plan):
    cheapest = scenario(golden_plan, OptimizationMode.CHEAPEST)
    balanced = scenario(golden_plan, OptimizationMode.BALANCED)
    one = scenario(golden_plan, OptimizationMode.ONE_STORE)
    for s in (cheapest, balanced, one):
        assert s.status == PlanStatus.OK and s.optimization_status == OptimizationStatus.OPTIMAL
    assert (cheapest.checkout_total_minor, cheapest.store_count) == (20400, 3)
    assert (balanced.checkout_total_minor, balanced.store_count) == (24000, 2)
    assert (one.checkout_total_minor, one.store_count) == (26900, 1)
    assert cheapest.checkout_total_minor <= balanced.checkout_total_minor <= one.checkout_total_minor


def test_golden_explanation_numbers_come_from_engine(golden_plan):
    balanced = scenario(golden_plan, OptimizationMode.BALANCED)
    one = scenario(golden_plan, OptimizationMode.ONE_STORE)
    assert balanced.net_saving_vs_one_store_minor == (one.checkout_total_minor - balanced.checkout_total_minor) - (balanced.travel_cost_minor - one.travel_cost_minor)
    assert any("ONE_STORE" in e for e in balanced.explanations)
    assert balanced.confidence.verified_share_of_checkout == 1
    assert len(balanced.pantry_uses) >= 1 and all(pu.state == "CONFIRMED" for pu in balanced.pantry_uses)


def test_member_only_offer_not_used_without_membership(golden_plan):
    for s in golden_plan.scenarios:
        assert all(p.canonical_product_id != "PORK_MINCED" for p in s.purchases)
    assert any("frikadeller" in w for w in golden_plan.coverage_warnings)


def test_snapshot_records_offers_and_versions(golden_plan):
    snap = golden_plan.data_snapshot
    used = {p.offer_id for s in golden_plan.scenarios for p in s.purchases}
    assert set(snap.offer_ids) == used and all(oid in snap.offer_versions for oid in used)
    assert golden_plan.optimizer_version.startswith("cpsat-")
    assert set(snap.weights) == {"CHEAPEST", "BALANCED", "ONE_STORE"}


def test_reproducible(demo_data):
    from hjemmefra.planning.service import generate_plan
    from tests.conftest import make_request
    data, _ = demo_data
    a = generate_plan(make_request(optimization_modes=[OptimizationMode.BALANCED], days=4), data)
    b = generate_plan(make_request(optimization_modes=[OptimizationMode.BALANCED], days=4), data)
    assert [m.recipe_id for m in a.scenarios[0].meals] == [m.recipe_id for m in b.scenarios[0].meals]
    assert a.scenarios[0].checkout_total_minor == b.scenarios[0].checkout_total_minor
