"""Run one or more optimization modes over a context; handle infeasibility honestly."""
from __future__ import annotations

from typing import Dict, List, Optional

from hjemmefra.core.metrics import OPTIMIZER_RUNTIME, PLAN_GENERATION, registry
from hjemmefra.domain.plan import BudgetMode, OptimizationMode, OptimizationStatus, PlanStatus, Scenario
from hjemmefra.optimization.context import OptimizationContext
from hjemmefra.optimization.explain import explain_scenario, explain_tradeoffs
from hjemmefra.optimization.model import build_and_solve
from hjemmefra.optimization.result import build_scenario
from hjemmefra.optimization.weights import weights_for


def run_mode(mode: OptimizationMode, ctx: OptimizationContext, relax_budget: bool = False) -> Scenario:
    req = ctx.request
    w, ov = weights_for(mode, req)
    budget = None if relax_budget else req.budget_minor
    out = build_and_solve(ctx, w, max_stores=ov["max_stores"], budget_mode=ov["budget_mode"],
                          min_price_confidence=ov["min_price_confidence"], budget_minor=budget,
                          time_limit=req.time_limit_seconds, allow_leftovers=req.allow_leftover_meals,
                          max_recipe_repeats=req.max_recipe_repeats, seed=req.deterministic_seed)
    registry.observe(OPTIMIZER_RUNTIME, out.wall_time, mode=mode.value, status=out.status.value)
    sc = build_scenario(mode, ctx, out)
    if relax_budget:
        sc.relaxed_constraints.append("BUDGET")
        sc.warnings.append("NEXT_BEST_PLAN: overskrider det angivne budget.")
    if sc.status == PlanStatus.NO_FEASIBLE_PLAN:
        sc.infeasibility_reason = diagnose(ctx, ov, sc.infeasibility_reason)
        if req.budget_minor is not None and ov["budget_mode"] == BudgetMode.HARD:
            # compute minimum required budget with checkout-only objective and no budget constraint
            probe = build_and_solve(ctx, w, max_stores=ov["max_stores"], budget_mode=BudgetMode.SOFT,
                                    min_price_confidence=ov["min_price_confidence"], budget_minor=None,
                                    time_limit=req.time_limit_seconds, allow_leftovers=req.allow_leftover_meals,
                                    max_recipe_repeats=req.max_recipe_repeats, seed=req.deterministic_seed,
                                    objective_checkout_only=True)
            if probe.objective is not None:
                sc.minimum_estimated_required_budget_minor = probe.checkout_minor
                sc.infeasibility_reason = (f"BUDGET_INFEASIBLE: billigste mulige plan koster {probe.checkout_minor / 100:.2f} kr, "
                                           f"budget er {req.budget_minor / 100:.2f} kr")
    registry.inc(PLAN_GENERATION, status=sc.status.value, mode=mode.value)
    sc.explanations = explain_scenario(sc, ctx)
    return sc


def diagnose(ctx: OptimizationContext, ov: dict, fallback: Optional[str]) -> str:
    if not ctx.candidates:
        return "NO_RECIPE_CANDIDATES: ingen opskrifter opfylder de hårde krav (allergener, kost, tid eller prisdata)."
    if not ctx.stores:
        return "NO_STORES_IN_RANGE: ingen butikker inden for den tilladte afstand."
    if len(ctx.candidates) < len(ctx.days) and ctx.request.max_recipe_repeats == 1 and not ctx.request.allow_leftover_meals:
        return "TOO_FEW_CANDIDATES: færre gyldige opskrifter end dage uden gentagelser."
    return fallback or "MODEL_INFEASIBLE"


def run_scenarios(ctx: OptimizationContext) -> List[Scenario]:
    scenarios: List[Scenario] = []
    modes = ctx.request.optimization_modes or [OptimizationMode.BALANCED]
    for mode in modes:
        sc = run_mode(mode, ctx)
        scenarios.append(sc)
        if sc.status == PlanStatus.NO_FEASIBLE_PLAN and sc.minimum_estimated_required_budget_minor is not None:
            nb = run_mode(mode, ctx, relax_budget=True)
            if nb.status == PlanStatus.OK:
                scenarios.append(nb)
    explain_tradeoffs(scenarios)
    return scenarios
