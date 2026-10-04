from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel

from hjemmefra.core.units import Unit
from hjemmefra.domain.product import StorageType


class Leftover(BaseModel):
    leftover_id: str
    description: str
    quantity: Decimal
    unit: Unit
    origin_meal_day: date
    origin_recipe_id: str
    available_from: date
    expiry: date
    expiry_is_estimate: bool = True
    storage: StorageType = StorageType.CHILLED
    reserved_for: Optional[date] = None
    consumed: bool = False
