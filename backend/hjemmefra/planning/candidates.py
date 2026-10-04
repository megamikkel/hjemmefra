"""Recipe candidate generation and pruning (requirement 27/28).

Pipeline: hard filters (allergens, diet, exclusions, prep time, servings) ->
coverage check (every required ingredient has a pantry source or a purchase
option) -> ranking by cheapest standalone cost + preference -> Top-K.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_CEILING, Decimal
from typing import Dict, List, Optional, Sequence

from hjemmefra.core.units import Quantity, Unit
from hjemmefra.domain.household import Allergen, DietType, Household
from hjemmefra.domain.plan import PlanRequest
from hjemmefra.domain.product import CanonicalProduct
from hjemmefra.domain.recipe import Recipe, RecipeIngredient
from hjemmefra.matching.ingredient_product import PurchaseOption, product_violates_hard_constraints
from hjemmefra.planning.scoring import ScoreBreakdown, preference_score
from hjemmefra.pricing.engine import PriceUnavailable, product_cost_for_packages


@dataclass
class ScaledIngredient:
    ingredient_id: str
    base_qty: Decimal  # scaled, in product base unit
    optional: bool


@dataclass
class RecipeCandidate:
    recipe: Recipe
    servings: int
    scale: Decimal
    ingredients: List[ScaledIngredient]
    score: ScoreBreakdown
    standalone_cost_minor: Optional[int]  # cheapest cover ignoring pantry; None if any price unknown
    uncoverable: List[str] = field(default_factory=list)


def hard_filter(recipe: Recipe, household: Household, products: Dict[str, CanonicalProduct], req: PlanRequest) -> Optional[str]:
    p = household.preferences
    if set(recipe.allergens) & set(p.allergens):
        return "ALLERGEN"
    max_prep = req.max_prep_minutes or p.max_prep_minutes
    if max_prep is not None and recipe.total_minutes > max_prep:
        return "MAX_PREP_TIME"
    for ing in recipe.ingredients:
        prod = products.get(ing.canonical_ingredient_id)
        if prod is None:
            if not ing.optional:
                return f"UNKNOWN_INGREDIENT:{ing.canonical_ingredient_id}"
            continue
        v = product_violates_hard_constraints(prod, household)
        if v and not ing.optional:
            # a substitute could still rescue a group ingredient; keep strict for allergens/exclusions
            if v.startswith("ALLERGEN") or v == "EXCLUDED_INGREDIENT" or not ing.substitution_group:
                return v
    if p.diet and p.diet not in recipe.dietary_tags and p.diet in (DietType.VEGAN, DietType.VEGETARIAN):
        # recipe not tagged for the diet -> check products
        for ing in recipe.ingredients:
            prod = products.get(ing.canonical_ingredient_id)
            if prod and product_violates_hard_constraints(prod, household) and not ing.optional:
                return f"DIET:{p.diet.value}"
    return None


def scale_recipe(recipe: Recipe, servings: int, products: Dict[str, CanonicalProduct]) -> List[ScaledIngredient]:
    scale = Decimal(servings) / Decimal(recipe.servings)
    out: List[ScaledIngredient] = []
    for ing in recipe.ingredients:
        prod = products.get(ing.canonical_ingredient_id)
        q = Quantity(ing.quantity * scale, ing.unit)
        if prod is not None and q.dimension != Quantity(Decimal(1), prod.base_unit).dimension:
            if prod.density_g_per_ml is None:
                raise PriceUnavailable(f"UNIT_CONVERSION_UNKNOWN:{ing.canonical_ingredient_id}")
            q = q.convert_to(prod.base_unit, prod.density_g_per_ml)
        base = q.to_base().value.quantize(Decimal(1), rounding=ROUND_CEILING)
        out.append(ScaledIngredient(ing.canonical_ingredient_id, base, ing.optional))
    return out


def standalone_cost(ingredients: List[ScaledIngredient], options: Dict[str, List[PurchaseOption]]) -> tuple[Optional[int], List[str]]:
    total = 0
    missing: List[str] = []
    for si in ingredients:
        opts = options.get(si.ingredient_id) or []
        best: Optional[int] = None
        for o in opts:
            n = int((si.base_qty / o.package_base_qty).to_integral_value(rounding=ROUND_CEILING)) if si.base_qty > 0 else 0
            try:
                c = product_cost_for_packages(o.offer, max(n, 1)).checkout_minor
            except PriceUnavailable:
                continue
            best = c if best is None or c < best else best
        if best is None:
            if not si.optional:
                missing.append(si.ingredient_id)
            continue
        total += best
    return (None if missing else total), missing


def generate_candidates(recipes: Sequence[Recipe], household: Household, products: Dict[str, CanonicalProduct],
                        options: Dict[str, List[PurchaseOption]], pantry_base: Dict[str, Decimal], req: PlanRequest,
                        servings: int) -> tuple[List[RecipeCandidate], List[dict]]:
    cands: List[RecipeCandidate] = []
    rejected: List[dict] = []
    for r in recipes:
        why = hard_filter(r, household, products, req)
        if why:
            rejected.append({"recipe_id": r.recipe_id, "reason": why})
            continue
        try:
            scaled = scale_recipe(r, servings, products)
        except PriceUnavailable as exc:
            rejected.append({"recipe_id": r.recipe_id, "reason": str(exc)})
            continue
        cost, missing = standalone_cost(scaled, options)
        # an ingredient fully covered by pantry is not "missing"
        still_missing = [m for m in missing if pantry_base.get(m, Decimal(0)) < next(s.base_qty for s in scaled if s.ingredient_id == m)]
        if still_missing:
            rejected.append({"recipe_id": r.recipe_id, "reason": "PRICE_UNKNOWN_OR_NO_OPTION", "ingredients": still_missing})
            continue
        score = preference_score(r, household, req.start_date)
        cands.append(RecipeCandidate(r, servings, Decimal(servings) / Decimal(r.servings), scaled, score, cost, []))
    # rank: cheaper and better liked first; deterministic tiebreak
    cands.sort(key=lambda c: ((c.standalone_cost_minor or 0) - c.score.total * 300, c.recipe.recipe_id))
    limit = max(req.candidate_limit_per_day, req.days + 2)
    return cands[:limit], rejected
