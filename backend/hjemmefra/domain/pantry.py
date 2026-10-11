from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel

from hjemmefra.core.units import Unit
from hjemmefra.domain.product import StorageType


class InventoryState(str, Enum):
    CONFIRMED = "CONFIRMED"
    ESTIMATED = "ESTIMATED"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class InventorySource(str, Enum):
    MANUAL = "MANUAL"
    PLAN_PURCHASE = "PLAN_PURCHASE"
    PACKAGE_REMAINDER = "PACKAGE_REMAINDER"
    RECEIPT_IMPORT = "RECEIPT_IMPORT"


class InventoryLot(BaseModel):
    lot_id: str
    household_id: str
    canonical_product_id: str
    quantity: Decimal
    unit: Unit
    purchase_date: Optional[date] = None
    expiry_date: Optional[date] = None
    expiry_is_estimate: bool = True
    opened: Optional[bool] = None
    state: InventoryState = InventoryState.CONFIRMED
    source: InventorySource = InventorySource.MANUAL
    storage: Optional[StorageType] = None
    version: int = 1


class PantrySnapshot(BaseModel):
    household_id: str
    version: int
    lots: list[InventoryLot]
