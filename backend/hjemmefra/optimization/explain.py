"""Explanations derived strictly from structured engine output. An LLM may later
rephrase these strings but must not change the numbers."""
from __future__ import annotations

from typing import List

from hjemmefra.domain.plan import OptimizationMode, PlanStatus, Scenario
from hjemmefra.optimization.context import OptimizationContext


def kr(minor: int | None) -> str:
    return "ukendt" if minor is None else f"{minor / 100:.2f} kr".replace(".", ",")


def explain_scenario(sc: Scenario, ctx: OptimizationContext) -> List[str]:
    if sc.status != PlanStatus.OK:
        return [f"{sc.mode.value}: NO_FEASIBLE_PLAN. {sc.infeasibility_reason}"]
    lines = [f"{sc.mode.value}: {kr(sc.checkout_total_minor)} ved kassen fordelt på {sc.store_count} butik(ker)."]
    if sc.optimization_status.value != "OPTIMAL":
        lines.append(f"Status {sc.optimization_status.value}: løsningen er gyldig men ikke bevist optimal.")
    if sc.pantry_uses:
        lines.append(f"{len(sc.pantry_uses)} eksisterende pantry-varer bruges.")
    if sc.leftover_uses:
        lines.append(f"{len(sc.leftover_uses)} ret(ter) laves i dobbelt portion og spises som rest dagen efter.")
    if sc.waste:
        if sc.waste.reused_in_later_meals_grams > 0:
            lines.append(f"{sc.waste.reused_in_later_meals_grams / 1000:.1f} kg råvarer indgår i flere måltider.".replace(".", ","))
        lines.append(f"Estimeret ubrugt mad: {len(sc.waste.unused_items)} rest(er) til en værdi af {kr(sc.waste.total_unused_value_minor)} (flyttes til projected inventory).")
    if sc.confidence:
        lines.append(f"{int(sc.confidence.verified_share_of_checkout * 100)} % af checkout-prisen bygger på verificerede aktuelle priser.")
    if sc.verified_saving_minor is not None:
        lines.append(f"Besparelse mod referencepris: {kr(sc.verified_saving_minor)} (sikkerhed {sc.saving_confidence.value}).")
    if sc.travel_cost_minor:
        lines.append(f"Estimeret transport: {kr(sc.travel_cost_minor)} (luftlinje × omvejsfaktor, ikke rutet kørsel).")
    for sb in sc.store_breakdown:
        lines.append(f"{sb.store_name}: {len(sb.lines)} varer, {kr(sb.checkout_minor)}, ca. {sb.distance_km} km ({sb.distance_method}).")
    return lines


def explain_tradeoffs(scenarios: List[Scenario]) -> None:
    ok = [s for s in scenarios if s.status == PlanStatus.OK]
    by_mode = {s.mode: s for s in ok if not s.relaxed_constraints}
    one = by_mode.get(OptimizationMode.ONE_STORE)
    cheapest = by_mode.get(OptimizationMode.CHEAPEST)
    for s in ok:
        if one is not None and s is not one:
            gross = one.checkout_total_minor - s.checkout_total_minor
            net = gross - (s.travel_cost_minor - one.travel_cost_minor)
            s.net_saving_vs_one_store_minor = net
            s.explanations.append(f"Mod ONE_STORE ({kr(one.checkout_total_minor)}, 1 butik): brutto {kr(gross)} billigere, "
                                  f"netto {kr(net)} efter estimeret ekstra transport.")
        if cheapest is not None and s is not cheapest:
            diff = s.checkout_total_minor - cheapest.checkout_total_minor
            s.explanations.append(f"Den absolut billigste plan (CHEAPEST) kostede {kr(cheapest.checkout_total_minor)} med "
                                  f"{cheapest.store_count} butik(ker); denne plan koster {kr(diff)} mere og bruger {s.store_count} butik(ker).")
