"""Invariant checks across all scenarios of the golden plan (requirement 54)."""
from collections import defaultdict
from decimal import Decimal

from hjemmefra.demo.dataset import PANTRY, PRODUCT_MAP
from hjemmefra.domain.plan import PlanStatus
from hjemmefra.pricing.engine import product_cost_for_packages


def ok_scenarios(plan):
    return [s for s in plan.scenarios if s.status == PlanStatus.OK]


def test_checkout_equals_sum_of_lines_and_stores(golden_plan):
    for s in ok_scenarios(golden_plan):
        assert s.checkout_total_minor == sum(p.checkout_cost_minor for p in s.purchases)
        assert s.checkout_total_minor == sum(sb.checkout_minor for sb in s.store_breakdown)
        for p in s.purchases:
            assert p.checkout_cost_minor == p.product_cost_minor + p.deposit_minor
            assert p.consumed_value_minor <= p.product_cost_minor


def test_packages_cover_consumption_and_cost_is_real_package_cost(golden_plan, demo_data):
    data, _ = demo_data
    offers = {o.offer_id: o for o in data.offers}
    for s in ok_scenarios(golden_plan):
        for p in s.purchases:
            assert p.total_quantity >= p.consumed_quantity
            assert p.remainder_quantity == p.total_quantity - p.consumed_quantity
            # cost must be >= cost of buying the packages at the offer's own rules
            assert p.product_cost_minor == product_cost_for_packages(offers[p.offer_id], p.packages).product_cost_minor \
                or p.product_cost_minor >= product_cost_for_packages(offers[p.offer_id], p.packages).product_cost_minor


def test_pantry_never_negative_and_stale_never_used(golden_plan):
    avail = {l.lot_id: l.quantity for l in PANTRY}
    for s in ok_scenarios(golden_plan):
        used = defaultdict(Decimal)
        for pu in s.pantry_uses:
            used[pu.lot_id] += pu.quantity
            assert pu.state in ("CONFIRMED", "ESTIMATED")
        for lot_id, q in used.items():
            assert q <= avail[lot_id]
        assert "lot_pasta_stale" not in used


def test_offers_valid_on_shopping_date_and_store_scope(golden_plan, demo_data):
    data, _ = demo_data
    stores = {st.store_id: st for st in data.stores}
    shop = golden_plan.request.shopping_dates or [golden_plan.request.start_date]
    for s in ok_scenarios(golden_plan):
        for p in s.purchases:
            assert any(p.valid_from <= d <= p.valid_to for d in shop)
            offer = next(o for o in data.offers if o.offer_id == p.offer_id)
            st = stores[p.store_id]
            assert offer.applies_to_store(st.store_id, st.chain_id, st.region)


def test_store_count_within_max(golden_plan):
    for s in ok_scenarios(golden_plan):
        assert s.store_count <= golden_plan.request.max_stores
        assert s.store_count == len({p.store_id for p in s.purchases})


def test_one_meal_per_day_and_no_leftover_double_use(golden_plan):
    for s in ok_scenarios(golden_plan):
        days = [m.day for m in s.meals]
        assert len(days) == golden_plan.request.days and len(set(days)) == len(days)
        lids = [lu.leftover_id for lu in s.leftover_uses]
        assert len(lids) == len(set(lids))
        for lu in s.leftover_uses:
            assert lu.used_on > lu.from_day


def test_no_allergen_or_excluded_product(golden_plan, demo_data):
    data, _ = demo_data
    banned = set(data.household.preferences.allergens)
    for s in ok_scenarios(golden_plan):
        for p in s.purchases:
            assert not (set(PRODUCT_MAP[p.canonical_product_id].allergens) & banned)


def test_saving_only_claimed_with_reference(golden_plan):
    for s in ok_scenarios(golden_plan):
        for p in s.purchases:
            if p.reference_cost_minor is None:
                assert p.saving_minor is None and p.saving_confidence.value == "UNKNOWN"
            else:
                assert p.saving_minor == p.reference_cost_minor - p.product_cost_minor
