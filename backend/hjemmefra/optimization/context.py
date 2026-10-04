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
    options: Dict[str, List[PurchaseOption]]  # ingredient -> options
    pantry: Dict[str, List[UsableLot]]  # ingredient -> usable lots (FEFO)
    stores: Dict[str, StoreDistance]
    travel_cost: Dict[str, int]  # store_id -> øre
    products: Dict[str, CanonicalProduct]
    history: List[PriceObservation] = field(default_factory=list)
    servings: int = 2
    shopping_dates: List[date] = field(default_factory=list)

    def pantry_base(self) -> Dict[str, Decimal]:
        return {k: sum((u.usable_base_qty for u in v), Decimal(0)) for k, v in self.pantry.items()}
