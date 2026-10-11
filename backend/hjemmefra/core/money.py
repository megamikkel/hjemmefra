"""Money handling.

All monetary values are stored as integer minor units (øre for DKK) with an
explicit currency. Decimal is used for the public representation; floats are
never used for money. See ADR-0003.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Union

Number = Union[int, str, Decimal]


@dataclass(frozen=True, slots=True, order=False)
class Money:
    minor: int  # integer minor units (øre)
    currency: str = "DKK"

    # ----- construction -------------------------------------------------
    @classmethod
    def from_decimal(cls, value: Number, currency: str = "DKK") -> "Money":
        if isinstance(value, float):  # pragma: no cover - defensive
            raise TypeError("Money must not be constructed from float")
        d = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return cls(int(d * 100), currency)

    @classmethod
    def zero(cls, currency: str = "DKK") -> "Money":
        return cls(0, currency)

    # ----- representation -----------------------------------------------
    @property
    def amount(self) -> Decimal:
        return (Decimal(self.minor) / Decimal(100)).quantize(Decimal("0.01"))

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"

    # ----- arithmetic ---------------------------------------------------
    def _check(self, other: "Money") -> None:
        if not isinstance(other, Money):
            raise TypeError("Money arithmetic requires Money operands")
        if other.currency != self.currency:
            raise ValueError(f"Currency mismatch: {self.currency} vs {other.currency}")

    def __add__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.minor + other.minor, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.minor - other.minor, self.currency)

    def __mul__(self, factor: int) -> "Money":
        if not isinstance(factor, int):
            raise TypeError("Money can only be multiplied by an integer count")
        return Money(self.minor * factor, self.currency)

    __rmul__ = __mul__

    def __neg__(self) -> "Money":
        return Money(-self.minor, self.currency)

    def __lt__(self, other: "Money") -> bool:
        self._check(other)
        return self.minor < other.minor

    def __le__(self, other: "Money") -> bool:
        self._check(other)
        return self.minor <= other.minor

    def __gt__(self, other: "Money") -> bool:
        self._check(other)
        return self.minor > other.minor

    def __ge__(self, other: "Money") -> bool:
        self._check(other)
        return self.minor >= other.minor

    def is_positive(self) -> bool:
        return self.minor > 0

    def per_unit(self, quantity: Decimal) -> Decimal:
        """Price per one unit of quantity, as Decimal (not Money) with 4 decimals."""
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        return (self.amount / quantity).quantize(Decimal("0.0001"))


def sum_money(items, currency: str = "DKK") -> Money:
    total = Money.zero(currency)
    for m in items:
        total = total + m
    return total
