"""Pantry usability rules.

Only CONFIRMED and ESTIMATED lots that have not expired on the usage date may
reduce the shopping list. STALE / UNKNOWN lots are reported but never counted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

from hjemmefra.core.units import Quantity, Unit, compatible
from hjemmefra.domain.pantry import InventoryLot, InventoryState
from hjemmefra.domain.product import CanonicalProduct

STALE_AFTER_DAYS = 30  # a manual lot not confirmed within this window becomes STALE


@dataclass
class UsableLot:
    lot: InventoryLot
    usable_base_qty: Decimal  # in product base unit


def effective_state(lot: InventoryLot, today: date) -> InventoryState:
    if lot.state in (InventoryState.STALE, InventoryState.UNKNOWN):
        return lot.state
    if lot.purchase_date and (today - lot.purchase_date).days > STALE_AFTER_DAYS and lot.state == InventoryState.ESTIMATED:
        return InventoryState.STALE
    return lot.state


def usable_lots(lots: Iterable[InventoryLot], products: Dict[str, CanonicalProduct], use_by: date) -> Dict[str, List[UsableLot]]:
    out: Dict[str, List[UsableLot]] = {}
    for lot in lots:
        state = effective_state(lot, use_by)
        if state not in (InventoryState.CONFIRMED, InventoryState.ESTIMATED):
            continue
        if lot.expiry_date and lot.expiry_date < use_by:
            continue
        if lot.quantity <= 0:
            continue
        p = products.get(lot.canonical_product_id)
        if p is None or not compatible(lot.unit, p.base_unit):
            continue
        q = Quantity(lot.quantity, lot.unit).to_base().value
        out.setdefault(lot.canonical_product_id, []).append(UsableLot(lot, q))
    # earliest expiry first (use perishables first)
    for k in out:
        out[k].sort(key=lambda u: (u.lot.expiry_date or date.max, u.lot.lot_id))
    return out


def allocate(lots: List[UsableLot], needed_base: Decimal) -> List[tuple[UsableLot, Decimal]]:
    """Allocate needed quantity across lots (FEFO). Never drives a lot negative."""
    alloc: List[tuple[UsableLot, Decimal]] = []
    remaining = needed_base
    for u in lots:
        if remaining <= 0:
            break
        take = min(u.usable_base_qty, remaining)
        if take > 0:
            alloc.append((u, take))
            remaining -= take
    return alloc
