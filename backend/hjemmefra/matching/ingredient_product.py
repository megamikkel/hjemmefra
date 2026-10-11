"""Ingredient <-> purchasable product matching.

For each recipe ingredient produce compatible purchase options (offer at a
concrete store, or a known regular price), with an explanation. Matching is
attribute based (canonical id, substitution group, required attributes,
allergens, diet, fresh/frozen), never fuzzy text alone.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Sequence

from hjemmefra.core.confidence import Confidence, MatchConfidence
from hjemmefra.core.units import Quantity, compatible
from hjemmefra.domain.household import Allergen, DietType, Household
from hjemmefra.domain.offer import NormalizedOffer
from hjemmefra.domain.product import CanonicalProduct, StorageType
from hjemmefra.domain.recipe import RecipeIngredient
from hjemmefra.domain.store import Store
from hjemmefra.ingestion.validation import usable_for_pricing
from hjemmefra.pricing.engine import eligibility


@dataclass
class PurchaseOption:
    option_id: str
    canonical_id: str  # product actually bought (may be a substitute within group)
    ingredient_id: str  # ingredient it satisfies
    store: Store
    offer: NormalizedOffer
    package_base_qty: Decimal  # in ingredient base unit
    price_confidence: Confidence
    explanation: str
    is_substitute: bool = False


@dataclass
class MatchReport:
    options: Dict[str, List[PurchaseOption]] = field(default_factory=dict)  # requirement_key -> options
    accepted_products: Dict[str, set] = field(default_factory=dict)  # requirement_key -> canonical ids that satisfy it
    rejected: List[dict] = field(default_factory=list)


def requirement_key(ing: RecipeIngredient) -> str:
    """Key for 'what is needed': canonical id plus the recipe's own constraints, so two recipes
    needing the same canonical ingredient with different requirements (e.g. fat <= 12 %) are not
    conflated, while identical requirements aggregate across recipes."""
    import json
    from hjemmefra.core.ids import stable_hash
    if not ing.required_attributes and ing.accepts_frozen and ing.substitution_group is None:
        return ing.canonical_ingredient_id
    sig = json.dumps({"a": ing.required_attributes, "f": ing.accepts_frozen, "g": ing.substitution_group}, sort_keys=True, default=str)
    return f"{ing.canonical_ingredient_id}#{stable_hash(sig)[:8]}"


def product_violates_hard_constraints(product: CanonicalProduct, household: Household) -> Optional[str]:
    prefs = household.preferences
    if set(product.allergens) & set(prefs.allergens):
        return f"ALLERGEN:{','.join(a.value for a in set(product.allergens) & set(prefs.allergens))}"
    if product.canonical_id in prefs.excluded_ingredients:
        return "EXCLUDED_INGREDIENT"
    a = product.attributes
    if prefs.diet in (DietType.VEGETARIAN, DietType.PESCETARIAN) and not a.vegetarian:
        if not (prefs.diet == DietType.PESCETARIAN and product.protein_group == "FISH"):
            return f"DIET:{prefs.diet.value}"
    if prefs.diet == DietType.VEGAN and not a.vegan:
        return "DIET:VEGAN"
    if prefs.diet == DietType.HALAL and a.halal is False:
        return "DIET:HALAL"
    if prefs.diet == DietType.GLUTEN_FREE and Allergen.GLUTEN in product.allergens:
        return "DIET:GLUTEN_FREE"
    if prefs.diet == DietType.LACTOSE_FREE and Allergen.LACTOSE in product.allergens:
        return "DIET:LACTOSE_FREE"
    return None


def _attributes_ok(product: CanonicalProduct, ing: RecipeIngredient) -> Optional[str]:
    req = ing.required_attributes or {}
    a = product.attributes
    if "fat_percentage_max" in req and a.fat_percentage is not None and a.fat_percentage > Decimal(str(req["fat_percentage_max"])):
        return "fat percentage too high"
    if "fat_percentage_min" in req and a.fat_percentage is not None and a.fat_percentage < Decimal(str(req["fat_percentage_min"])):
        return "fat percentage too low"
    if req.get("organic") and not a.organic:
        return "organic required"
    if not ing.accepts_frozen and a.storage == StorageType.FROZEN:
        return "frozen not accepted"
    return None


def candidate_products(ing: RecipeIngredient, products: Dict[str, CanonicalProduct]) -> List[tuple[CanonicalProduct, bool]]:
    """Exact product first, then members of the ingredient's substitution group."""
    out: List[tuple[CanonicalProduct, bool]] = []
    exact = products.get(ing.canonical_ingredient_id)
    if exact:
        out.append((exact, False))
    group = ing.substitution_group or (exact.substitution_group if exact else None)
    if group:
        for p in products.values():
            if p.substitution_group == group and p.canonical_id != ing.canonical_ingredient_id:
                out.append((p, True))
    return out


def match_ingredients(ingredients: Iterable[RecipeIngredient], products: Dict[str, CanonicalProduct],
                      offers: Sequence[NormalizedOffer], stores: Sequence[Store], household: Household,
                      shopping_dates: Sequence[date], min_confidence: Confidence = Confidence.MEDIUM) -> MatchReport:
    report = MatchReport()
    seen: set[str] = set()
    for ing in ingredients:
        key = requirement_key(ing)
        if key in seen:
            continue
        seen.add(key)
        opts: List[PurchaseOption] = []
        accepted: set = set()
        for product, is_sub in candidate_products(ing, products):
            why_not = product_violates_hard_constraints(product, household) or _attributes_ok(product, ing)
            if why_not:
                report.rejected.append({"ingredient": ing.canonical_ingredient_id, "product": product.canonical_id, "reason": why_not})
                continue
            accepted.add(product.canonical_id)
            for offer in offers:
                if offer.canonical_product_id != product.canonical_id:
                    continue
                if offer.match_confidence in (MatchConfidence.LOW, MatchConfidence.UNMATCHED):
                    report.rejected.append({"ingredient": ing.canonical_ingredient_id, "offer": offer.offer_id, "reason": "LOW_MATCH_CONFIDENCE"})
                    continue
                if not usable_for_pricing(offer, min_confidence):
                    report.rejected.append({"ingredient": ing.canonical_ingredient_id, "offer": offer.offer_id,
                                            "reason": f"NOT_USABLE:{offer.validation_status.value}/{offer.price_confidence.value}"})
                    continue
                if not any(offer.is_valid_on(d) for d in shopping_dates):
                    report.rejected.append({"ingredient": ing.canonical_ingredient_id, "offer": offer.offer_id, "reason": "EXPIRED_ON_SHOPPING_DATE"})
                    continue
                block = eligibility(offer, household)
                if block:
                    report.rejected.append({"ingredient": ing.canonical_ingredient_id, "offer": offer.offer_id, "reason": block})
                    continue
                pkg = Quantity(offer.package_quantity * offer.package_count, offer.package_unit)  # type: ignore[arg-type]
                if not compatible(pkg.unit, ing.unit):
                    if product.density_g_per_ml is None:
                        report.rejected.append({"ingredient": ing.canonical_ingredient_id, "offer": offer.offer_id, "reason": "UNIT_CONVERSION_UNKNOWN"})
                        continue
                    pkg = pkg.convert_to(ing.unit, product.density_g_per_ml)
                for store in stores:
                    if not offer.applies_to_store(store.store_id, store.chain_id, store.region):
                        continue
                    expl = (f"{ing.canonical_ingredient_id} matched '{offer.raw_title}' at {store.name}: "
                            f"canonical {product.canonical_id}" + (" (substitute in group)" if is_sub else "") +
                            f", {pkg.value.normalize()} {pkg.unit.value}/pkg, price confidence {offer.price_confidence.value}, "
                            f"valid {offer.valid_from}..{offer.valid_to}, scope {offer.scope.value}")
                    opts.append(PurchaseOption(
                        option_id=f"{offer.offer_id}@{store.store_id}",
                        canonical_id=product.canonical_id,
                        ingredient_id=key,
                        store=store, offer=offer,
                        package_base_qty=pkg.to_base().value,
                        price_confidence=offer.price_confidence,
                        explanation=expl, is_substitute=is_sub,
                    ))
        report.options[key] = opts
        report.accepted_products[key] = accepted
    return report
