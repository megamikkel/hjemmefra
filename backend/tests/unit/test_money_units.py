from decimal import Decimal

import pytest

from hjemmefra.core.money import Money, sum_money
from hjemmefra.core.units import Quantity, Unit, UnitConversionUnknown, UnknownUnit, compatible, parse_unit


def test_money_decimal_roundtrip():
    m = Money.from_decimal("29.95")
    assert m.minor == 2995 and str(m) == "29.95 DKK"
    assert (m + Money.from_decimal("0.05")).minor == 3000
    assert (m * 3).minor == 8985


def test_money_rejects_float_and_mixed_currency():
    with pytest.raises(TypeError):
        Money.from_decimal(1.1)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Money(100, "DKK") + Money(100, "EUR")
    with pytest.raises(TypeError):
        Money(100) * 1.5  # type: ignore[operator]


def test_sum_money_exact():
    assert sum_money([Money.from_decimal("0.10")] * 10).minor == 100


def test_unit_conversion_same_dimension():
    assert Quantity(Decimal("1.5"), Unit.KG).to_base().value == Decimal("1500")
    assert Quantity(Decimal(2), Unit.DL).convert_to(Unit.ML).value == Decimal(200)


def test_unit_conversion_cross_dimension_blocked():
    with pytest.raises(UnitConversionUnknown):
        Quantity(Decimal(500), Unit.ML).convert_to(Unit.G)
    assert not compatible(Unit.ML, Unit.G)


def test_unit_conversion_with_documented_density():
    q = Quantity(Decimal(500), Unit.ML).convert_to(Unit.G, density_g_per_ml=Decimal("1.03"))
    assert q.value == Decimal("515.00")


def test_parse_unit_aliases_and_unknown():
    assert parse_unit("Stk.") == Unit.STK
    assert parse_unit("ltr") == Unit.L
    with pytest.raises(UnknownUnit):
        parse_unit("bundt")
