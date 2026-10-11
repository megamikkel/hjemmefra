from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from hjemmefra.domain.household import Household
from hjemmefra.domain.offer import PriceObservation
from hjemmefra.domain.pantry import InventoryLot
from hjemmefra.domain.plan import PlanRequest
from hjemmefra.domain.product import CanonicalProduct
from hjemmefra.domain.store import StoreDistance
from hjemmefra.matching.ingredient_product import PurchaseOption
from hjemmefra.pantry.service import UsableLot
from hjemmefra.planning.candidates import RecipeCandidate


@dataclass
class OptimizationContext:
    household: Household
    request: PlanRequest
    days: List[date]
    candidates: List[RecipeCandidate]
    options: Dict[str, List[PurchaseOption]]  # requirement key -> options
    pantry: Dict[str, List[UsableLot]]  # canonical id -> usable lots (FEFO)
    stores: Dict[str, StoreDistance]
    travel_cost: Dict[str, int]  # store_id -> øre
    products: Dict[str, CanonicalProduct]
    accepted_products: Dict[str, set] = field(default_factory=dict)  # requirement key -> canonical ids
    history: List[PriceObservation] = field(default_factory=list)
    servings: int = 2
    shopping_dates: List[date] = field(default_factory=list)

    def pantry_base(self) -> Dict[str, Decimal]:
        """Usable pantry quantity per canonical id."""
        return {k: sum((u.usable_base_qty for u in v), Decimal(0)) for k, v in self.pantry.items()}

    def pantry_for_key(self, key: str) -> Dict[str, Decimal]:
        """Usable pantry per canonical id that satisfies the requirement key."""
        base = self.pantry_base()
        cids = self.accepted_products.get(key) or {key.split("#")[0]}
        return {c: base[c] for c in cids if base.get(c, Decimal(0)) > 0}

    def all_options(self) -> Dict[str, PurchaseOption]:
        out: Dict[str, PurchaseOption] = {}
        for opts in self.options.values():
            for o in opts:
                out.setdefault(o.option_id, o)
        return out
