"""Translate a SolveOutput into a structured Scenario (all numbers from the engine)."""
from __future__ import annotations

from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List

from hjemmefra.core.confidence import Confidence, min_confidence
from hjemmefra.core.units import Unit
from hjemmefra.domain.plan import (Availability, ConfidenceSummary, LeftoverUse, Meal, OptimizationMode, OptimizationStatus,
                                   PantryUse, PlanStatus, PurchaseLine, Scenario, StoreBreakdown, WasteEstimate)
from hjemmefra.leftovers.engine import LeftoverLedger
from hjemmefra.optimization.context import OptimizationContext
from hjemmefra.optimization.model import SolveOutput
from hjemmefra.pantry.service import allocate
from hjemmefra.pricing.engine import consumed_value, product_cost_for_packages, reference_price


def build_scenario(mode: OptimizationMode, ctx: OptimizationContext, out: SolveOutput) -> Scenario:
    sc = Scenario(mode=mode, status=PlanStatus.OK, optimization_status=out.status, objective_value=out.objective,
                  solver_wall_time_seconds=round(out.wall_time, 4))
    if out.status in (OptimizationStatus.INFEASIBLE, OptimizationStatus.ERROR) or out.objective is None:
        sc.status = PlanStatus.NO_FEASIBLE_PLAN
        sc.infeasibility_reason = out.infeasibility_reason
        return sc
    if out.status == OptimizationStatus.TIME_LIMIT:
        sc.warnings.append("Løsningen blev fundet inden for tidsgrænsen, men er ikke bevist optimal.")

    # ---- purchases ----------------------------------------------------
    purchased_qty: Dict[str, Decimal] = {}
    lines: List[PurchaseLine] = []
    for key, eff in out.eff.items():
        if eff <= 0:
            continue
        ing, option_id = key.split("|", 1)
        o = next(op for op in ctx.options[ing] if op.option_id == option_id)
        cost = product_cost_for_packages(o.offer, out.n[key])
        total_q = o.package_base_qty * eff
        purchased_qty[ing] = purchased_qty.get(ing, Decimal(0)) + total_q
        lines.append((ing, o, cost, total_q))

    # consumed per ingredient = demand - pantry used (pantry consumed first)
    consumed_from_purchase: Dict[str, Decimal] = {}
    for ing, dem in out.demand.items():
        consumed_from_purchase[ing] = max(Decimal(0), Decimal(dem) - Decimal(out.u.get(ing, 0)))

    purchase_lines: List[PurchaseLine] = []
    # distribute consumption across lines of same ingredient proportionally (deterministic order)
    remaining_consume = dict(consumed_from_purchase)
    for ing, o, cost, total_q in sorted(lines, key=lambda t: (t[0], t[1].option_id)):
        prod = ctx.products.get(o.canonical_id)
        base_unit = prod.base_unit if prod else o.offer.package_unit
        take = min(total_q, remaining_consume.get(ing, Decimal(0)))
        remaining_consume[ing] = remaining_consume.get(ing, Decimal(0)) - take
        ref_pkg, method, ref_conf = reference_price(o.offer, ctx.history)
        ref_total = ref_pkg * cost.packages if ref_pkg is not None else None
        saving = (ref_total - cost.product_cost_minor) if ref_total is not None else None
        pkg_qty_base = o.package_base_qty
        purchase_lines.append(PurchaseLine(
            canonical_product_id=o.canonical_id, product_name=prod.name if prod else o.offer.raw_title,
            store_id=o.store.store_id, store_name=o.store.name, offer_id=o.offer.offer_id,
            price_source="OFFER" if o.offer.offer_price_minor != o.offer.normal_price_minor else "REGULAR_PRICE",
            packages=cost.packages, package_quantity=pkg_qty_base, package_unit=base_unit,  # type: ignore[arg-type]
            total_quantity=total_q, consumed_quantity=take, remainder_quantity=total_q - take,
            product_cost_minor=cost.product_cost_minor, deposit_minor=cost.deposit_minor, checkout_cost_minor=cost.checkout_minor,
            consumed_value_minor=consumed_value(cost.product_cost_minor, total_q, take),
            reference_cost_minor=ref_total, reference_method=method, saving_minor=saving,
            saving_confidence=ref_conf if saving is not None else Confidence.UNKNOWN,
            price_confidence=o.price_confidence, availability=Availability.OFFERED,
            valid_from=o.offer.valid_from, valid_to=o.offer.valid_to, multi_buy_applied=cost.multi_buy_applied,
            explanation=o.explanation + (f"; {cost.packages} pakke(r) købes, {take.normalize()} {base_unit.value} bruges, "
                                         f"{(total_q - take).normalize()} {base_unit.value} til rest/pantry"),
        ))
    sc.purchases = purchase_lines

    # ---- pantry uses ----------------------------------------------------
    for ing, used in out.u.items():
        if used <= 0:
            continue
        for lot, qty in allocate(ctx.pantry.get(ing, []), Decimal(used)):
            sc.pantry_uses.append(PantryUse(canonical_product_id=ing, lot_id=lot.lot.lot_id, quantity=qty,
                                            unit=ctx.products[ing].base_unit, state=lot.lot.state.value))

    # ---- meals & leftovers -------------------------------------------------
    ledger = LeftoverLedger()
    cost_by_ing: Dict[str, int] = {}
    for pl in purchase_lines:
        cost_by_ing[pl.canonical_product_id] = cost_by_ing.get(pl.canonical_product_id, 0) + pl.consumed_value_minor
    meals: List[Meal] = []
    for d, day in enumerate(ctx.days):
        for r, c in enumerate(ctx.candidates):
            cooked = out.x.get((d, r), 0) or out.z.get((d, r), 0)
            if not cooked:
                continue
            double = bool(out.z.get((d, r), 0))
            contrib = _meal_contribution(c, out, cost_by_ing, double)
            reasons = list(c.score.reasons)
            reasons += _ingredient_reasons(c, out, ctx)
            if double:
                reasons.append(f"laves i dobbelt portion; resten spises {day + timedelta(days=1)}")
            meals.append(Meal(day=day, recipe_id=c.recipe.recipe_id, recipe_name=c.recipe.name,
                              servings=c.servings * (2 if double else 1), total_minutes=c.recipe.total_minutes,
                              checkout_contribution_minor=contrib // (2 if double else 1), reasons=reasons, cooked_on=day))
            if double:
                lo = ledger.produce(f"{c.recipe.name} (rest)", Decimal(c.servings), Unit.PORTION, day, c.recipe.recipe_id)
                ledger.consume(lo.leftover_id, day + timedelta(days=1))
                meals.append(Meal(day=day + timedelta(days=1), recipe_id=c.recipe.recipe_id, recipe_name=c.recipe.name,
                                  servings=c.servings, is_leftover_meal=True, cooked_on=day, total_minutes=5,
                                  checkout_contribution_minor=contrib - contrib // 2,
                                  reasons=[f"rest fra {day}", "ingen ekstra indkøb"]))
                sc.leftover_uses.append(LeftoverUse(leftover_id=lo.leftover_id, description=lo.description,
                                                    from_day=day, used_on=day + timedelta(days=1)))
    sc.meals = sorted(meals, key=lambda mm: mm.day)

    # ---- stores ------------------------------------------------------------
    for sid, visited in out.y.items():
        if not visited:
            continue
        sl = [pl for pl in purchase_lines if pl.store_id == sid]
        sd = ctx.stores[sid]
        sc.store_breakdown.append(StoreBreakdown(
            store_id=sid, store_name=sd.store.name, chain_id=sd.store.chain_id, lines=sl,
            subtotal_minor=sum(l.product_cost_minor for l in sl), deposit_minor=sum(l.deposit_minor for l in sl),
            checkout_minor=sum(l.checkout_cost_minor for l in sl), distance_km=sd.distance_km,
            distance_method=sd.distance_method, travel_cost_minor=ctx.travel_cost.get(sid, 0)))
    sc.store_count = len(sc.store_breakdown)
    sc.checkout_total_minor = out.checkout_minor
    sc.deposit_total_minor = sum(l.deposit_minor for l in purchase_lines)
    sc.travel_cost_minor = out.travel_minor
    sc.store_penalty_minor = out.store_penalty_minor

    # ---- reference / saving ------------------------------------------------
    refs = [l.reference_cost_minor for l in purchase_lines]
    if purchase_lines and all(r is not None for r in refs):
        sc.reference_total_minor = sum(refs)  # type: ignore[arg-type]
        sc.verified_saving_minor = sc.reference_total_minor - sum(l.product_cost_minor for l in purchase_lines)
        sc.saving_confidence = min_confidence(*[l.saving_confidence for l in purchase_lines])
    elif purchase_lines:
        known = [l for l in purchase_lines if l.reference_cost_minor is not None]
        sc.verified_saving_minor = sum(l.saving_minor or 0 for l in known) if known else None
        sc.saving_confidence = Confidence.LOW if known else Confidence.UNKNOWN
        sc.warnings.append("Referencepris mangler for nogle varer; besparelsen er delvis.")

    # ---- waste --------------------------------------------------------
    unused = []
    unused_value = 0
    reused_g = Decimal(0)
    for pl in purchase_lines:
        if pl.remainder_quantity > 0:
            val = pl.product_cost_minor - pl.consumed_value_minor
            unused.append({"canonical_product_id": pl.canonical_product_id, "quantity": str(pl.remainder_quantity),
                           "unit": pl.package_unit.value, "value_minor": val, "note": "flyttes til projected inventory"})
            unused_value += val
    # ingredients consumed across more than one meal count as reuse
    for ing, dem in out.demand.items():
        meals_using = [c for r, c in enumerate(ctx.candidates) if any(out.x.get((d, r), 0) or out.z.get((d, r), 0) for d in range(len(ctx.days)))
                       and any(si.ingredient_id == ing for si in c.ingredients)]
        if len(meals_using) > 1 and ctx.products.get(ing) and ctx.products[ing].base_unit.value == "g":
            reused_g += Decimal(dem)
    sc.waste = WasteEstimate(unused_items=unused, total_unused_value_minor=unused_value, reused_in_later_meals_grams=reused_g)

    # ---- confidence ---------------------------------------------------------
    verified = sum(l.checkout_cost_minor for l in purchase_lines if l.price_confidence.at_least(Confidence.HIGH))
    unverified = sum(l.checkout_cost_minor for l in purchase_lines if not l.price_confidence.at_least(Confidence.HIGH))
    total = verified + unverified
    share = (Decimal(verified) / Decimal(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if total else Decimal(1)
    overall = Confidence.VERIFIED if unverified == 0 else (Confidence.HIGH if share >= Decimal("0.9") else Confidence.MEDIUM)
    sc.confidence = ConfidenceSummary(verified_share_of_checkout=share, verified_total_minor=verified,
                                      unverified_total_minor=unverified, unknown_price_items=[], overall=overall)
    if unverified:
        sc.warnings.append(f"{int((1 - share) * 100)} % af checkout-prisen bygger på priser med lavere sikkerhed.")
    return sc


def _meal_contribution(c, out: SolveOutput, cost_by_ing: Dict[str, int], double: bool) -> int:
    total = 0
    for si in c.ingredients:
        dem = out.demand.get(si.ingredient_id, 0)
        if dem <= 0:
            continue
        share = Decimal(int(si.base_qty) * (2 if double else 1)) / Decimal(dem)
        total += int((Decimal(cost_by_ing.get(si.ingredient_id, 0)) * share).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return total


def _ingredient_reasons(c, out: SolveOutput, ctx: OptimizationContext) -> List[str]:
    reasons: List[str] = []
    for si in c.ingredients:
        if out.u.get(si.ingredient_id, 0) > 0:
            reasons.append(f"{ctx.products[si.ingredient_id].name} findes allerede i pantry")
        for key, eff in out.eff.items():
            ing, oid = key.split("|", 1)
            if ing == si.ingredient_id and eff > 0:
                o = next(op for op in ctx.options[ing] if op.option_id == oid)
                if o.offer.normal_price_minor and o.offer.offer_price_minor and o.offer.offer_price_minor < o.offer.normal_price_minor:
                    reasons.append(f"{ctx.products[o.canonical_id].name} er på tilbud i {o.store.name} (prissikkerhed {o.price_confidence.value})")
                break
    reasons.append(f"retten tager {c.recipe.total_minutes} minutter")
    return reasons
