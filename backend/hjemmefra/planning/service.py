"""Plan generation orchestration: offers -> matching -> candidates -> optimization -> PlanResult."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Sequence

from hjemmefra import OPTIMIZER_VERSION
from hjemmefra.core.ids import new_id
from hjemmefra.core.metrics import CANDIDATE_COUNT, registry
from hjemmefra.domain.household import Household
from hjemmefra.domain.offer import NormalizedOffer, PriceObservation
from hjemmefra.domain.pantry import InventoryLot
from hjemmefra.domain.plan import DataSnapshot, PlanRequest, PlanResult
from hjemmefra.domain.product import CanonicalProduct
from hjemmefra.domain.recipe import Recipe
from hjemmefra.domain.store import Store
from hjemmefra.location.geo import DistanceProvider, filter_stores
from hjemmefra.location.travel import TravelConfig, travel_cost_minor
from hjemmefra.matching.ingredient_product import match_ingredients
from hjemmefra.optimization.context import OptimizationContext
from hjemmefra.optimization.scenarios import run_scenarios
from hjemmefra.optimization.weights import weights_for
from hjemmefra.pantry.service import usable_lots
from hjemmefra.planning.candidates import generate_candidates


@dataclass
class PlanningData:
    household: Household
    stores: Sequence[Store]
    offers: Sequence[NormalizedOffer]
    products: Dict[str, CanonicalProduct]
    recipes: Sequence[Recipe]
    pantry_lots: Sequence[InventoryLot]
    pantry_version: int
    history: Sequence[PriceObservation] = field(default_factory=list)
    coverage_warnings: List[str] = field(default_factory=list)


def generate_plan(req: PlanRequest, data: PlanningData, distance_provider: Optional[DistanceProvider] = None,
                  travel_cfg: TravelConfig = TravelConfig(), now: Optional[datetime] = None) -> PlanResult:
    now = now or datetime.now(timezone.utc)
    hh = data.household
    days = [req.start_date + timedelta(days=i) for i in range(req.days)]
    shopping_dates = req.shopping_dates or [req.start_date]
    servings = req.servings_per_meal or hh.default_servings()
    warnings = list(data.coverage_warnings)

    if req.pantry_version is not None and req.pantry_version != data.pantry_version:
        warnings.append(f"Pantry version {req.pantry_version} requested but current is {data.pantry_version}; plan uses current.")

    # 1. stores
    distances = filter_stores(hh.location, data.stores, req.max_distance_km, req.selected_store_ids, distance_provider)
    store_map = {d.store.store_id: d for d in distances}
    travel = {sid: travel_cost_minor(d, travel_cfg) for sid, d in store_map.items()}

    # 2. offers valid on a shopping date and applicable to a candidate store (done in matching)
    offers = [o for o in data.offers if any(o.is_valid_on(d) for d in shopping_dates)]

    # 3. ingredient -> purchase options
    all_ings = [i for r in data.recipes for i in r.ingredients]
    report = match_ingredients(all_ings, data.products, offers, [d.store for d in distances], hh, shopping_dates,
                               min_confidence=req.min_price_confidence)

    # 4. pantry
    pantry = usable_lots(data.pantry_lots, data.products, use_by=days[0])
    pantry_cid = {k: sum((u.usable_base_qty for u in v)) for k, v in pantry.items()}
    # pantry usable per requirement key = sum over accepted canonical products
    pantry_base = {key: sum((pantry_cid.get(c, 0) for c in cids), Decimal(0)) for key, cids in report.accepted_products.items()}

    # 5. candidates
    cands, rejected = generate_candidates(data.recipes, hh, data.products, report.options, pantry_base, req, servings)
    registry.observe(CANDIDATE_COUNT, len(cands))
    if not cands:
        warnings.append("Ingen opskrifter kunne prissættes med verificerede tilbud i de valgte butikker.")

    ctx = OptimizationContext(household=hh, request=req, days=days, candidates=cands, options=report.options,
                              pantry=pantry, accepted_products=report.accepted_products, stores=store_map, travel_cost=travel, products=data.products,
                              history=list(data.history), servings=servings, shopping_dates=shopping_dates)
    scenarios = run_scenarios(ctx)

    used_offer_ids = sorted({pl.offer_id for s in scenarios for pl in s.purchases if pl.offer_id})
    snapshot = DataSnapshot(
        snapshot_id=new_id("snap"), created_at=now, offer_ids=used_offer_ids,
        offer_versions={o.offer_id: o.version for o in offers if o.offer_id in used_offer_ids},
        recipe_versions={r.recipe_id: r.version for r in data.recipes},
        product_versions={p.canonical_id: p.version for p in data.products.values()},
        pantry_version=data.pantry_version, household_version=hh.version,
        weights={m.value: weights_for(m, req)[0] for m in req.optimization_modes},
    )
    for rj in rejected[:20]:
        warnings.append(f"Opskrift {rj['recipe_id']} udeladt: {rj['reason']}")
    return PlanResult(plan_id=new_id("plan"), household_id=hh.household_id, created_at=now, optimizer_version=OPTIMIZER_VERSION,
                      request=req, data_snapshot=snapshot, scenarios=scenarios, coverage_warnings=warnings)
