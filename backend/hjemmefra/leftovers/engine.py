"""Leftover ledger: a resource-flow model preventing double spending."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from hjemmefra.core.ids import new_id
from hjemmefra.core.units import Unit
from hjemmefra.domain.leftover import Leftover
from hjemmefra.domain.product import StorageType

DEFAULT_COOKED_SHELF_LIFE_DAYS = 2  # conservative category rule; always flagged as estimate


class LeftoverConflict(Exception):
    pass


class LeftoverLedger:
    def __init__(self) -> None:
        self._items: Dict[str, Leftover] = {}

    def produce(self, description: str, quantity: Decimal, unit: Unit, origin_day: date, recipe_id: str,
                shelf_life_days: int = DEFAULT_COOKED_SHELF_LIFE_DAYS, storage: StorageType = StorageType.CHILLED) -> Leftover:
        lo = Leftover(leftover_id=new_id("lo"), description=description, quantity=quantity, unit=unit,
                      origin_meal_day=origin_day, origin_recipe_id=recipe_id, available_from=origin_day + timedelta(days=1),
                      expiry=origin_day + timedelta(days=shelf_life_days), expiry_is_estimate=True, storage=storage)
        self._items[lo.leftover_id] = lo
        return lo

    def reserve(self, leftover_id: str, for_day: date) -> Leftover:
        lo = self._items[leftover_id]
        if lo.consumed:
            raise LeftoverConflict(f"{leftover_id} already consumed")
        if lo.reserved_for is not None and lo.reserved_for != for_day:
            raise LeftoverConflict(f"{leftover_id} already reserved for {lo.reserved_for}")
        if for_day < lo.available_from:
            raise LeftoverConflict(f"{leftover_id} not available before {lo.available_from}")
        if for_day > lo.expiry:
            raise LeftoverConflict(f"{leftover_id} expires {lo.expiry} (estimate) before {for_day}")
        lo.reserved_for = for_day
        return lo

    def consume(self, leftover_id: str, on_day: date) -> Leftover:
        lo = self.reserve(leftover_id, on_day)
        lo.consumed = True
        return lo

    def available(self, on_day: date) -> List[Leftover]:
        return [l for l in self._items.values() if not l.consumed and l.reserved_for is None
                and l.available_from <= on_day <= l.expiry]

    def all(self) -> List[Leftover]:
        return list(self._items.values())
