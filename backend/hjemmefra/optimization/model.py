"""CP-SAT model for joint meal-plan + basket optimization (ADR-0002).

Decision variables
  x[d,r]       recipe r cooked on day d (covers day d)
  z[d,r]       recipe r cooked double on day d, leftover covers day d+1
  n[o]         packages requested of purchase option o (offer @ store), pooled across recipes
  alloc[o,k]   base quantity from option o allocated to requirement k
  u[k,c]       pantry base quantity of canonical product c consumed for requirement k
  y[s]         store s visited
Constraints: one meal per day, recipe repeat cap, requirement coverage, option
allocation <= quantity bought, pantry conservation per canonical product, store
linking, max stores, hard budget. Objective: generalized cost in hundredths of øre.
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
    option_id: str
    canonical_id: str
    store_id: str
    pkg: int
    n: cp_model.IntVar
    eff_packages: cp_model.IntVar
    cost: cp_model.IntVar
    deposit: cp_model.IntVar
    qty: cp_model.IntVar
    cost_ub: int
    deposit_ub: int
    qty_ub: int
    alloc: Dict[str, cp_model.IntVar] = field(default_factory=dict)  # requirement key -> allocated base qty


@dataclass
class SolveOutput:
    status: OptimizationStatus
    objective: Optional[int]  # øre
    wall_time: float
    x: Dict[Tuple[int, int], int] = field(default_factory=dict)
    z: Dict[Tuple[int, int], int] = field(default_factory=dict)
    n: Dict[str, int] = field(default_factory=dict)  # option_id -> requested packages
    eff: Dict[str, int] = field(default_factory=dict)  # option_id -> packages actually bought
    alloc: Dict[Tuple[str, str], int] = field(default_factory=dict)  # (option_id, key) -> base qty
    u: Dict[Tuple[str, str], int] = field(default_factory=dict)  # (key, canonical_id) -> pantry base used
    y: Dict[str, int] = field(default_factory=dict)
    demand: Dict[str, int] = field(default_factory=dict)  # key -> base qty
    checkout_minor: int = 0
    travel_minor: int = 0
    store_penalty_minor: int = 0
    waste_penalty_minor: int = 0
    infeasibility_reason: Optional[str] = None

    def pantry_used_by_cid(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for (_, cid), v in self.u.items():
            out[cid] = out.get(cid, 0) + v
        return out

    def consumed_by_option(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for (oid, _), v in self.alloc.items():
            out[oid] = out.get(oid, 0) + v
        return out


def waste_rate_for(ctx: OptimizationContext, canonical_id: str) -> int:
    p = ctx.products.get(canonical_id)
    if p is None:
        return WASTE_RATE_CHILLED
    if p.base_unit.value == "stk":
        return WASTE_RATE_COUNT
    if p.attributes.storage in (StorageType.AMBIENT, StorageType.FROZEN):
        return WASTE_RATE_AMBIENT
    if p.estimated_shelf_life_days is not None and p.estimated_shelf_life_days <= PERISHABLE_SHELF_LIFE_DAYS:
        return WASTE_RATE_PERISHABLE
    return WASTE_RATE_CHILLED


def _status(st, wall, time_limit):
    if st == cp_model.OPTIMAL:
        return OptimizationStatus.OPTIMAL
    if st == cp_model.FEASIBLE:
        return OptimizationStatus.TIME_LIMIT if wall >= time_limit * 0.95 else OptimizationStatus.FEASIBLE
    return None


def build_and_solve(ctx: OptimizationContext, weights: ObjectiveWeights, max_stores: int, budget_mode: BudgetMode,
                    min_price_confidence: Confidence, budget_minor: Optional[int], time_limit: float,
                    allow_leftovers: bool, max_recipe_repeats: int, seed: int = 0,
                    objective_checkout_only: bool = False) -> SolveOutput:
    m = cp_model.CpModel()
    D = len(ctx.days)
    R = len(ctx.candidates)
    if R == 0:
        return SolveOutput(OptimizationStatus.INFEASIBLE, None, 0.0, infeasibility_reason="NO_RECIPE_CANDIDATES")

    # ---- meals -------------------------------------------------------------
    x = {(d, r): m.NewBoolVar(f"x_{d}_{r}") for d in range(D) for r in range(R)}
    z: Dict[Tuple[int, int], cp_model.IntVar] = {}
    for d in range(D - 1):
        for r, c in enumerate(ctx.candidates):
            if allow_leftovers and c.recipe.leftover_friendly:
                z[(d, r)] = m.NewBoolVar(f"z_{d}_{r}")
    for d in range(D):
        terms = [x[(d, r)] for r in range(R)]
        terms += [z[(d, r)] for r in range(R) if (d, r) in z]
        terms += [z[(d - 1, r)] for r in range(R) if (d - 1, r) in z]
        m.Add(sum(terms) == 1)
    for r in range(R):
        cooks = [x[(d, r)] for d in range(D)] + [z[(d, r)] for d in range(D) if (d, r) in z]
        m.Add(sum(cooks) <= max_recipe_repeats)

    # ---- demand per requirement key ----------------------------------------
    keys = sorted({si.ingredient_id for c in ctx.candidates for si in c.ingredients if not si.optional})
    demand: Dict[str, cp_model.IntVar] = {}
    max_demand: Dict[str, int] = {}
    for k in keys:
        terms, ub = [], 0
        for r, c in enumerate(ctx.candidates):
            q = sum(int(si.base_qty) for si in c.ingredients if si.ingredient_id == k and not si.optional)
            if q == 0:
                continue
            ub += q * 2 * max_recipe_repeats
            for d in range(D):
                terms.append(q * x[(d, r)])
                if (d, r) in z:
                    terms.append(2 * q * z[(d, r)])
        demand[k] = m.NewIntVar(0, ub, f"dem_{k}")
        m.Add(demand[k] == sum(terms))
        max_demand[k] = ub

    # ---- purchase options (pooled per offer@store) -------------------------
    all_opts = ctx.all_options()
    compat: Dict[str, List[str]] = {k: [o.option_id for o in ctx.options.get(k, []) if o.price_confidence.at_least(min_price_confidence)] for k in keys}
    opt_vars: Dict[str, OptionVars] = {}
    store_options: Dict[str, List[OptionVars]] = {}
    low_conf_terms = []
    for oid in sorted({o for ks in compat.values() for o in ks}):
        o = all_opts[oid]
        pkg = int(o.package_base_qty)
        if pkg <= 0:
            continue
        need = sum(max_demand[k] for k in keys if oid in compat[k])
        nmax = min(MAX_PACKAGES_PER_OPTION, max(1, -(-need // pkg)))
        try:
            table = cost_table(o.offer, nmax)
        except PriceUnavailable:
            continue
        n = m.NewIntVar(0, nmax, f"n_{oid}")
        eff = m.NewIntVar(0, max(t.packages for t in table), f"eff_{oid}")
        cost = m.NewIntVar(0, max(t.product_cost_minor for t in table), f"c_{oid}")
        dep = m.NewIntVar(0, max(t.deposit_minor for t in table), f"dep_{oid}")
        qty_ub = max(t.packages for t in table) * pkg
        qty = m.NewIntVar(0, qty_ub, f"q_{oid}")
        m.AddElement(n, [t.packages for t in table], eff)
        m.AddElement(n, [t.product_cost_minor for t in table], cost)
        m.AddElement(n, [t.deposit_minor for t in table], dep)
        m.Add(qty == eff * pkg)
        ov = OptionVars(oid, o.canonical_id, o.store.store_id, pkg, n, eff, cost, dep, qty,
                        max(t.product_cost_minor for t in table), max(t.deposit_minor for t in table), qty_ub)
        for k in keys:
            if oid in compat[k]:
                ov.alloc[k] = m.NewIntVar(0, min(qty_ub, max_demand[k]), f"a_{oid}_{k}")
        m.Add(sum(ov.alloc.values()) <= qty)
        opt_vars[oid] = ov
        store_options.setdefault(o.store.store_id, []).append(ov)
        if not o.price_confidence.at_least(Confidence.HIGH):
            low_conf_terms.append(eff)

    # ---- pantry ------------------------------------------------------------------
    pantry_base = ctx.pantry_base()
    u: Dict[Tuple[str, str], cp_model.IntVar] = {}
    for k in keys:
        for cid, avail in ctx.pantry_for_key(k).items():
            u[(k, cid)] = m.NewIntVar(0, min(int(avail), max_demand[k]), f"u_{k}_{cid}")
    for cid, avail in pantry_base.items():
        vs = [v for (k, c), v in u.items() if c == cid]
        if vs:
            m.Add(sum(vs) <= int(avail))

    # ---- coverage ----------------------------------------------------------------
    for k in keys:
        supply = [opt_vars[oid].alloc[k] for oid in compat[k] if oid in opt_vars]
        pantry_terms = [v for (kk, _), v in u.items() if kk == k]
        pantry_avail = sum(int(a) for a in ctx.pantry_for_key(k).values())
        if not supply:
            # no purchasable option: forbid recipes whose need exceeds pantry
            for r, c in enumerate(ctx.candidates):
                if any(si.ingredient_id == k and not si.optional and int(si.base_qty) > pantry_avail for si in c.ingredients):
                    for d in range(D):
                        m.Add(x[(d, r)] == 0)
                        if (d, r) in z:
                            m.Add(z[(d, r)] == 0)
        m.Add(sum(supply) + sum(pantry_terms) >= demand[k])
        for a in supply + pantry_terms:  # redundant but tightens propagation
            m.Add(a <= demand[k])

    # ---- surplus / waste per option ----------------------------------------------
    surplus: Dict[str, cp_model.IntVar] = {}
    for oid, ov in opt_vars.items():
        surplus[oid] = m.NewIntVar(0, ov.qty_ub, f"sur_{oid}")
        m.Add(surplus[oid] == ov.qty - sum(ov.alloc.values()))

    # ---- stores ------------------------------------------------------------------
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

    # ---- totals / budget ----------------------------------------------------------
    checkout_ub = sum(ov.cost_ub + ov.deposit_ub for ov in opt_vars.values())
    checkout = m.NewIntVar(0, max(checkout_ub, 0), "checkout")
    m.Add(checkout == sum(ov.cost + ov.deposit for ov in opt_vars.values()))
    travel = sum(ctx.travel_cost.get(sid, 0) * y[sid] for sid in y)
    overrun = m.NewIntVar(0, max(checkout_ub, 0), "overrun")
    if budget_minor is not None and budget_mode == BudgetMode.HARD:
        m.Add(checkout <= budget_minor)
        m.Add(overrun == 0)
    elif budget_minor is not None:
        m.AddMaxEquality(overrun, [checkout - budget_minor, 0])
    else:
        m.Add(overrun == 0)

    # ---- preference, time, variety -----------------------------------------------
    pref_terms, time_terms = [], []
    for r, c in enumerate(ctx.candidates):
        for d in range(D):
            pref_terms.append(c.score.total * x[(d, r)])
            time_terms.append(c.recipe.total_minutes * x[(d, r)])
            if (d, r) in z:
                pref_terms.append(2 * c.score.total * z[(d, r)])
                time_terms.append(c.recipe.total_minutes * z[(d, r)])
    variety_terms = []
    for attr in ("main_protein", "dish_type", "carbohydrate"):
        for g in sorted({getattr(c.recipe, attr) for c in ctx.candidates if getattr(c.recipe, attr)}):
            members = [r for r, c in enumerate(ctx.candidates) if getattr(c.recipe, attr) == g]
            for d in range(D - 1):
                cooked_d = [x[(d, r)] for r in members] + [z[(d, r)] for r in members if (d, r) in z]
                cooked_n = [x[(d + 1, r)] for r in members] + [z[(d + 1, r)] for r in members if (d + 1, r) in z]
                pen = m.NewBoolVar(f"var_{attr}_{g}_{d}")
                m.Add(sum(cooked_d) + sum(cooked_n) - 1 <= pen)
                variety_terms.append(pen)
    waste_terms = [waste_rate_for(ctx, ov.canonical_id) * surplus[oid] for oid, ov in opt_vars.items()]

    S = OBJ_SCALE
    if objective_checkout_only:
        m.Minimize(checkout)
    else:
        m.Minimize(S * weights.checkout_cost * checkout + S * weights.travel_cost * travel
                   + S * weights.store_penalty_minor * extra_stores + weights.waste_weight * sum(waste_terms)
                   - S * weights.preference_weight_minor * sum(pref_terms)
                   + S * weights.time_penalty_minor_per_minute * sum(time_terms)
                   + S * weights.variety_penalty_minor * sum(variety_terms)
                   + S * weights.low_confidence_penalty_minor * sum(low_conf_terms)
                   + S * weights.budget_overrun_weight * overrun)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 1  # determinism (ADR-0002)
    solver.parameters.random_seed = seed
    solver.parameters.linearization_level = 2  # stronger LP relaxation for the allocation structure
    t0 = time.perf_counter()
    st = solver.Solve(m)
    wall = time.perf_counter() - t0
    status = _status(st, wall, time_limit)
    if status is None:
        if st == cp_model.INFEASIBLE:
            return SolveOutput(OptimizationStatus.INFEASIBLE, None, wall, infeasibility_reason="MODEL_INFEASIBLE")
        if st == cp_model.UNKNOWN:
            return SolveOutput(OptimizationStatus.TIME_LIMIT, None, wall, infeasibility_reason="NO_SOLUTION_WITHIN_TIME_LIMIT")
        return SolveOutput(OptimizationStatus.ERROR, None, wall, infeasibility_reason=solver.StatusName(st))

    out = SolveOutput(status, int(round(solver.ObjectiveValue() / (1 if objective_checkout_only else S))), wall)
    out.x = {k: solver.Value(v) for k, v in x.items()}
    out.z = {k: solver.Value(v) for k, v in z.items()}
    for oid, ov in opt_vars.items():
        out.n[oid] = solver.Value(ov.n)
        out.eff[oid] = solver.Value(ov.eff_packages)
        for k, a in ov.alloc.items():
            v = solver.Value(a)
            if v:
                out.alloc[(oid, k)] = v
    out.u = {kc: solver.Value(v) for kc, v in u.items() if solver.Value(v)}
    out.y = {s: solver.Value(v) for s, v in y.items()}
    out.demand = {k: solver.Value(v) for k, v in demand.items()}
    out.checkout_minor = solver.Value(checkout)
    out.travel_minor = sum(ctx.travel_cost.get(s, 0) for s, v in out.y.items() if v)
    out.store_penalty_minor = weights.store_penalty_minor * solver.Value(extra_stores)
    out.waste_penalty_minor = sum(waste_rate_for(ctx, ov.canonical_id) * solver.Value(surplus[oid]) for oid, ov in opt_vars.items()) // S
    return out
