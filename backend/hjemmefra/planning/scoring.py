"""Explainable preference scoring (v1, no ML).

score = sum of documented components; higher is better. Returned with the
component breakdown so the explanation layer can say *why*.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List

from hjemmefra.domain.household import Household
from hjemmefra.domain.recipe import Recipe


@dataclass
class ScoreBreakdown:
    total: int
    components: Dict[str, int] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)


def preference_score(recipe: Recipe, household: Household, plan_start: date) -> ScoreBreakdown:
    p = household.preferences
    comps: Dict[str, int] = {}
    reasons: List[str] = []
    rating = p.recipe_ratings.get(recipe.recipe_id)
    if rating is not None:
        comps["rating"] = (rating - 3) * 3  # 1..5 -> -6..+6
        reasons.append(f"familiens rating {rating}/5")
    if recipe.recipe_id in p.favorite_recipes:
        comps["favorite"] = 5
        reasons.append("favoritret")
    if recipe.cuisine and recipe.cuisine in p.liked_cuisines:
        comps["cuisine"] = 2
        reasons.append(f"foretrukket køkken ({recipe.cuisine})")
    ing_ids = {i.canonical_ingredient_id for i in recipe.ingredients}
    liked = ing_ids & set(p.liked_ingredients)
    disliked = ing_ids & set(p.disliked_ingredients)
    if liked:
        comps["liked_ingredients"] = 2 * len(liked)
        reasons.append("indeholder ingredienser familien kan lide")
    if disliked:
        comps["disliked_ingredients"] = -4 * len(disliked)
        reasons.append("indeholder ingredienser familien ikke bryder sig om")
    if p.less_meat and recipe.main_protein in ("VEG", "FISH"):
        comps["less_meat"] = 2
        reasons.append("mindre kød")
    if p.child_friendly and recipe.child_friendly:
        comps["child_friendly"] = 2
        reasons.append("børnevenlig")
    last = p.recently_eaten.get(recipe.recipe_id)
    if last is not None:
        days = (plan_start - last).days
        if days < 14:
            comps["recency"] = -(14 - days) // 2
            reasons.append(f"spist for {days} dage siden")
    return ScoreBreakdown(total=sum(comps.values()), components=comps, reasons=reasons)
