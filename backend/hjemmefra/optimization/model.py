"""CP-SAT model for joint meal-plan + basket optimization (ADR-0002).

Decision variables
  x[d,r]   recipe r cooked on day d (covers day d)
  z[d,r]   recipe r cooked double on day d, leftover covers day d+1
  n[o]     packages requested of purchase option o
  u[i]     pantry base quantity consumed for ingredient i
  y[s]     store s visited
Constraints: exactly one meal per day, recipe repeat cap, ingredient coverage,
store linking, max stores, hard budget. Objective: generalized cost in
hundredths of øre (OBJ_SCALE).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from ortools.sat.python import cp_model

from hjemmefra.core.confidence import Confidence
from hjemmefra.domain.plan import BudgetMode, ObjectiveWeights, OptimizationStatus
from hjemmefra.domain.product import StorageType
from hjemmefra.optimization.context import OptimizationContext
from hjemmefra.optimization.weights import (OBJ_SCALE, PERISHABLE_SHELF_LIFE_DAYS, WASTE_RATE_AMBIENT, WASTE_RATE_CHILLED,
                                           WASTE_RATE_COUNT, WASTE_RATE_PERISHABLE)
from hjemmefra.pricing.engine import PriceUnavailable, cost_table

MAX_PACKAGES_PER_OPTION = 12


@dataclass
class OptionVars:
    option_idx: int
    ingredient: str
    n: cp_model.IntVar  # requested packages
    eff_packages: cp_model.IntVar
    cost: cp_model.IntVar  # product cost øre
    deposit: cp_model.IntVar
    qty: cp_model.IntVar  # base units supplied
    table: list
    cost_ub: int = 0
    deposit_ub: int = 0
    qty_ub: int = 0


@dataclass
class SolveOutput:
    status: OptimizationStatus
    objective: Optional[int]  # in øre (scaled back)
    wall_time: float
    x: Dict[Tuple[int, int], int] = field(default_factory=dict)
    z: Dict[Tuple[int, int], int] = field(default_factory=dict)
    n: Dict[str, int] = field(default_factory=dict)  # option_id -> requested packages
    eff: Dict[str, int] = field(default_factory=dict)  # option_id -> effective packages bought
    u: Dict[str, int] = field(default_factory=dict)  # ingredient -> pantry base used
    y: Dict[str, int] = field(default_factory=dict)
    demand: Dict[str, int] = field(default_factory=dict)
    checkout_minor: int = 0
    travel_minor: int = 0
    store_penalty_minor: int = 0
    waste_penalty_minor: int = 0
    infeasibility_reason: Optional[str] = None


def waste_rate_for(ctx: OptimizationContext, ingredient_id: str) -> int:
    p = ctx.products.get(ingredient_id)
    if p is None:
        return WASTE_RATE_CHILLED
    if p.base_unit.value == "stk":
        return WASTE_RATE_COUNT
    if p.attributes.storage == StorageType.AMBIENT or p.attributes.storage == StorageType.FROZEN:
        return WASTE_RATE_AMBIENT
    if p.estimated_shelf_life_days is not None and p.estimated_shelf_life_days <= PERISHABLE_SHELF_LIFE_DAYS:
        return WASTE_RATE_PERISHABLE
    return WASTE_RATE_CHILLED


def build_and_solve(ctx: OptimizationContext, weights: ObjectiveWeights, max_stores: int, budget_mode: BudgetMode,
                    min_price_confidence: Confidence, budget_minor: Optional[int], time_limit: float,
                    allow_leftovers: bool, max_recipe_repeats: int, seed: int = 0,
                    objective_checkout_only: bool = False) -> SolveOutput:
    m = cp_model.CpModel()
    D = len(ctx.days)
    R = len(ctx.candidates)
    if R == 0:
        return SolveOutput(OptimizationStatus.INFEASIBLE, None, 0.0, infeasibility_reason="NO_RECIPE_CANDIDATES")

    x = {(d, r): m.NewBoolVar(f"x_{d}_{r}") for d in range(D) for r in range(R)}
    z: Dict[Tuple[int, int], cp_model.IntVar] = {}
    for d in range(D - 1):
        for r, c in enumerate(ctx.candidates):
            if allow_leftovers and c.recipe.leftover_friendly:
                z[(d, r)] = m.NewBoolVar(f"z_{d}_{r}")

    # one meal per day
    for d in range(D):
        terms = [x[(d, r)] for r in range(R)]
        terms += [z[(d, r)] for r in range(R) if (d, r) in z]
        terms += [z[(d - 1, r)] for r in range(R) if (d - 1, r) in z]
        m.Add(sum(terms) == 1)
    # repeats
    for r in range(R):
        cooks = [x[(d, r)] for d in range(D)] + [z[(d, r)] for d in range(D) if (d, r) in z]
        m.Add(sum(cooks) <= max_recipe_repeats)

    # demand per ingredient (base units)
    ingredients = sorted({si.ingredient_id for c in ctx.candidates for si in c.ingredients if not si.optional})
    demand: Dict[str, cp_model.IntVar] = {}
    max_demand: Dict[str, int] = {}
    for i in ingredients:
        terms = []
        ub = 0
        for r, c in enumerate(ctx.candidates):
            q = sum(int(si.base_qty) for si in c.ingredients if si.ingredient_id == i and not si.optional)
            if q == 0:
                continue
            ub += q * 2 * max_recipe_repeats
            for d in range(D):
                terms.append(q * x[(d, r)])
                if (d, r) in z:
                    terms.append(2 * q * z[(d, r)])
        demand[i] = m.NewIntVar(0, max(ub, 0), f"dem_{i}")
        m.Add(demand[i] == sum(terms))
        max_demand[i] = ub

    # purchase options
    opt_vars: List[OptionVars] = []
    store_options: Dict[str, List[OptionVars]] = {}
    low_conf_terms = []
    for i in ingredients:
        for k, o in enumerate(ctx.options.get(i, [])):
            if not o.price_confidence.at_least(min_price_confidence):
                continue
            pkg = int(o.package_base_qty)
            if pkg <= 0:
                continue
            nmax = min(MAX_PACKAGES_PER_OPTION, max(1, -(-max_demand[i] // pkg)))
            try:
                table = cost_table(o.offer, nmax)
            except PriceUnavailable:
                continue
            n = m.NewIntVar(0, nmax, f"n_{i}_{k}")
            eff = m.NewIntVar(0, max(t.packages for t in table), f"eff_{i}_{k}")
            cost = m.NewIntVar(0, max(t.product_cost_minor for t in table), f"c_{i}_{k}")
            dep = m.NewIntVar(0, max(t.deposit_minor for t in table), f"dep_{i}_{k}")
            qty = m.NewIntVar(0, max(t.packages for t in table) * pkg, f"q_{i}_{k}")
            m.AddElement(n, [t.packages for t in table], eff)
            m.AddElement(n, [t.product_cost_minor for t in table], cost)
            m.AddElement(n, [t.deposit_minor for t in table], dep)
            m.Add(qty == eff * pkg)
            ov = OptionVars(k, i, n, eff, cost, dep, qty, table,
                            cost_ub=max(t.product_cost_minor for t in table), deposit_ub=max(t.deposit_minor for t in table),
                            qty_ub=max(t.packages for t in table) * pkg)
            opt_vars.append(ov)
            store_options.setdefault(o.store.store_id, []).append(ov)
            if not o.price_confidence.at_least(Confidence.HIGH):
                low_conf_terms.append(eff)

    # pantry
    pantry_base = ctx.pantry_base()
    u: Dict[str, cp_model.IntVar] = {}
    for i in ingredients:
        avail = int(pantry_base.get(i, Decimal(0)))
        u[i] = m.NewIntVar(0, avail, f"u_{i}")

    # coverage + surplus
    surplus: Dict[str, cp_model.IntVar] = {}
    for i in ingredients:
        supply = [ov.qty for ov in opt_vars if ov.ingredient == i]
        if not supply and int(pantry_base.get(i, 0)) < max_demand[i]:
            # ingredient cannot be covered by any option: forbid recipes needing it
            for r, c in enumerate(ctx.candidates):
                if any(si.ingredient_id == i and not si.optional and si.base_qty > pantry_base.get(i, Decimal(0)) for si in c.ingredients):
                    for d in range(D):
                        m.Add(x[(d, r)] == 0)
                        if (d, r) in z:
                            m.Add(z[(d, r)] == 0)
        m.Add(sum(supply) + u[i] >= demand[i])
        ub = sum(ov.qty_ub for ov in opt_vars if ov.ingredient == i) + int(pantry_base.get(i, 0))
        surplus[i] = m.NewIntVar(0, max(ub, 0), f"sur_{i}")
        m.Add(surplus[i] == sum(supply) + u[i] - demand[i])

    # stores
    y: Dict[str, cp_model.IntVar] = {}
    for sid in ctx.stores:
        y[sid] = m.NewBoolVar(f"y_{sid}")
        for ov in store_options.get(sid, []):
            m.Add(ov.n <= MAX_PACKAGES_PER_OPTION * y[sid])
        if sid not in store_options:
            m.Add(y[sid] == 0)
    if y:
        m.Add(sum(y.values()) <= max_stores)
    store_count = m.NewIntVar(0, max(len(y), 1), "store_count")
    m.Add(store_count == sum(y.values()))
    extra_stores = m.NewIntVar(0, max(len(y), 1), "extra_stores")
    m.AddMaxEquality(extra_stores, [store_count - 1, 0])

    # totals
    checkout_ub = sum(ov.cost_ub + ov.deposit_ub for ov in opt_vars)
    checkout = m.NewIntVar(0, max(checkout_ub, 0), "checkout")
    m.Add(checkout == sum(ov.cost + ov.deposit for ov in opt_vars))
    travel = sum(ctx.travel_cost.get(sid, 0) * y[sid] for sid in y)

    # budget
    overrun = m.NewIntVar(0, max(checkout_ub, 0), "overrun")
    if budget_minor is not None:
        if budget_mode == BudgetMode.HARD:
            m.Add(checkout <= budget_minor)
            m.Add(overrun == 0)
        else:
            m.AddMaxEquality(overrun, [checkout - budget_minor, 0])
    else:
        m.Add(overrun == 0)

    # preference, time, variety
    pref_terms = []
    time_terms = []
    for r, c in enumerate(ctx.candidates):
        for d in range(D):
            pref_terms.append(c.score.total * x[(d, r)])
            time_terms.append(c.recipe.total_minutes * x[(d, r)])
            if (d, r) in z:
                pref_terms.append(2 * c.score.total * z[(d, r)])
                time_terms.append(c.recipe.total_minutes * z[(d, r)])
    variety_terms = []
    for attr in ("main_protein", "dish_type", "carbohydrate"):
        groups = sorted({getattr(c.recipe, attr) for c in ctx.candidates if getattr(c.recipe, attr)})
        for g in groups:
            members = [r for r, c in enumerate(ctx.candidates) if getattr(c.recipe, attr) == g]
            for d in range(D - 1):
                cooked_d = [x[(d, r)] for r in members] + [z[(d, r)] for r in members if (d, r) in z]
                cooked_n = [x[(d + 1, r)] for r in members] + [z[(d + 1, r)] for r in members if (d + 1, r) in z]
                pen = m.NewBoolVar(f"var_{attr}_{g}_{d}")
                m.Add(sum(cooked_d) + sum(cooked_n) - 1 <= pen)
                variety_terms.append(pen)

    waste_terms = [waste_rate_for(ctx, i) * surplus[i] for i in ingredients]

    S = OBJ_SCALE
    if objective_checkout_only:
        m.Minimize(checkout)
    else:
        m.Minimize(
            S * weights.checkout_cost * checkout
            + S * weights.travel_cost * travel
            + S * weights.store_penalty_minor * extra_stores
            + weights.waste_weight * sum(waste_terms)
            - S * weights.preference_weight_minor * sum(pref_terms)
            + S * weights.time_penalty_minor_per_minute * sum(time_terms)
            + S * weights.variety_penalty_minor * sum(variety_terms)
            + S * weights.low_confidence_penalty_minor * sum(low_conf_terms)
            + S * weights.budget_overrun_weight * overrun
        )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 1  # determinism (ADR-0002)
    solver.parameters.random_seed = seed
    t0 = time.perf_counter()
    st = solver.Solve(m)
    wall = time.perf_counter() - t0

    if st == cp_model.OPTIMAL:
        status = OptimizationStatus.OPTIMAL
    elif st == cp_model.FEASIBLE:
        status = OptimizationStatus.TIME_LIMIT if wall >= time_limit * 0.95 else OptimizationStatus.FEASIBLE
    elif st == cp_model.INFEASIBLE:
        return SolveOutput(OptimizationStatus.INFEASIBLE, None, wall, infeasibility_reason="MODEL_INFEASIBLE")
    elif st == cp_model.UNKNOWN:
        return SolveOutput(OptimizationStatus.TIME_LIMIT, None, wall, infeasibility_reason="NO_SOLUTION_WITHIN_TIME_LIMIT")
    else:
        return SolveOutput(OptimizationStatus.ERROR, None, wall, infeasibility_reason=solver.StatusName(st))

    out = SolveOutput(status, int(round(solver.ObjectiveValue() / (1 if objective_checkout_only else S))), wall)
    out.x = {k: solver.Value(v) for k, v in x.items()}
    out.z = {k: solver.Value(v) for k, v in z.items()}
    for ov in opt_vars:
        o = ctx.options[ov.ingredient][ov.option_idx]
        key = f"{ov.ingredient}|{o.option_id}"
        out.n[key] = solver.Value(ov.n)
        out.eff[key] = solver.Value(ov.eff_packages)
    out.u = {i: solver.Value(v) for i, v in u.items()}
    out.y = {s: solver.Value(v) for s, v in y.items()}
    out.demand = {i: solver.Value(v) for i, v in demand.items()}
    out.checkout_minor = solver.Value(checkout)
    out.travel_minor = sum(ctx.travel_cost.get(s, 0) for s, v in out.y.items() if v)
    out.store_penalty_minor = weights.store_penalty_minor * solver.Value(extra_stores)
    out.waste_penalty_minor = sum(waste_rate_for(ctx, i) * solver.Value(surplus[i]) for i in ingredients) // S
    return out
