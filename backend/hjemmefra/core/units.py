"""Unit system with dimension safety.

Conversions are only allowed within a dimension (mass, volume, count).
Cross-dimension conversion (e.g. ml -> g) requires an explicit, documented
product-specific density and otherwise yields UNIT_CONVERSION_UNKNOWN.
Base units: g (mass), ml (volume), stk (count). Quantities are kept as
Decimal; the optimizer uses integer base units.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional


class Dimension(str, Enum):
    MASS = "MASS"
    VOLUME = "VOLUME"
    COUNT = "COUNT"


class Unit(str, Enum):
    G = "g"
    KG = "kg"
    ML = "ml"
    CL = "cl"
    DL = "dl"
    L = "l"
    STK = "stk"
    PAKKE = "pakke"
    PORTION = "portion"
    TSK = "tsk"
    SPSK = "spsk"


_DIMENSION = {
    Unit.G: Dimension.MASS,
    Unit.KG: Dimension.MASS,
    Unit.ML: Dimension.VOLUME,
    Unit.CL: Dimension.VOLUME,
    Unit.DL: Dimension.VOLUME,
    Unit.L: Dimension.VOLUME,
    Unit.TSK: Dimension.VOLUME,
    Unit.SPSK: Dimension.VOLUME,
    Unit.STK: Dimension.COUNT,
    Unit.PAKKE: Dimension.COUNT,
    Unit.PORTION: Dimension.COUNT,
}

# factor to base unit of its dimension
_TO_BASE = {
    Unit.G: Decimal(1),
    Unit.KG: Decimal(1000),
    Unit.ML: Decimal(1),
    Unit.CL: Decimal(10),
    Unit.DL: Decimal(100),
    Unit.L: Decimal(1000),
    Unit.TSK: Decimal(5),
    Unit.SPSK: Decimal(15),
    Unit.STK: Decimal(1),
    Unit.PAKKE: Decimal(1),
    Unit.PORTION: Decimal(1),
}

BASE_UNIT = {Dimension.MASS: Unit.G, Dimension.VOLUME: Unit.ML, Dimension.COUNT: Unit.STK}

_ALIASES = {
    "g": Unit.G, "gram": Unit.G, "gr": Unit.G,
    "kg": Unit.KG, "kilo": Unit.KG,
    "ml": Unit.ML, "cl": Unit.CL, "dl": Unit.DL, "l": Unit.L, "liter": Unit.L, "ltr": Unit.L,
    "stk": Unit.STK, "stk.": Unit.STK, "styk": Unit.STK, "pcs": Unit.STK,
    "pk": Unit.PAKKE, "pakke": Unit.PAKKE, "pakker": Unit.PAKKE, "ps": Unit.PAKKE, "pose": Unit.PAKKE,
    "portion": Unit.PORTION, "port": Unit.PORTION,
    "tsk": Unit.TSK, "spsk": Unit.SPSK,
}


class UnitConversionUnknown(Exception):
    """Raised when a conversion is not safe (incompatible dimensions)."""


class UnknownUnit(Exception):
    """Raised when a unit token cannot be parsed."""


def parse_unit(token: str) -> Unit:
    key = token.strip().lower()
    if key in _ALIASES:
        return _ALIASES[key]
    raise UnknownUnit(token)


def dimension_of(unit: Unit) -> Dimension:
    return _DIMENSION[unit]


@dataclass(frozen=True, slots=True)
class Quantity:
    value: Decimal
    unit: Unit

    def __post_init__(self):
        if not isinstance(self.value, Decimal):
            object.__setattr__(self, "value", Decimal(str(self.value)))

    @property
    def dimension(self) -> Dimension:
        return dimension_of(self.unit)

    def to_base(self) -> "Quantity":
        return Quantity(self.value * _TO_BASE[self.unit], BASE_UNIT[self.dimension])

    def base_amount(self) -> Decimal:
        return self.to_base().value

    def convert_to(self, unit: Unit, density_g_per_ml: Optional[Decimal] = None) -> "Quantity":
        """Convert to `unit`. Mass<->volume only with explicit density."""
        src_dim, dst_dim = self.dimension, dimension_of(unit)
        base = self.to_base().value
        if src_dim == dst_dim:
            return Quantity(base / _TO_BASE[unit], unit)
        if density_g_per_ml is not None and {src_dim, dst_dim} == {Dimension.MASS, Dimension.VOLUME}:
            if src_dim == Dimension.VOLUME:
                grams = base * density_g_per_ml
                return Quantity(grams / _TO_BASE[unit], unit)
            ml = base / density_g_per_ml
            return Quantity(ml / _TO_BASE[unit], unit)
        raise UnitConversionUnknown(f"Cannot convert {self.unit.value} -> {unit.value} without density")

    def __str__(self) -> str:
        return f"{self.value.normalize()} {self.unit.value}"


def compatible(a: Unit, b: Unit) -> bool:
    return dimension_of(a) == dimension_of(b)
