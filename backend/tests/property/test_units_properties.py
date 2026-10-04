from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from hjemmefra.core.money import Money
from hjemmefra.core.units import Quantity, Unit, dimension_of

mass_units = st.sampled_from([Unit.G, Unit.KG])
vol_units = st.sampled_from([Unit.ML, Unit.CL, Unit.DL, Unit.L])


@given(v=st.decimals(min_value=Decimal("0.001"), max_value=Decimal("100000"), places=3), a=mass_units, b=mass_units)
def test_mass_roundtrip(v, a, b):
    q = Quantity(v, a).convert_to(b).convert_to(a)
    assert abs(q.value - v) < Decimal("0.000001")


@given(v=st.decimals(min_value=Decimal("0.001"), max_value=Decimal("100000"), places=3), a=vol_units, b=vol_units)
def test_volume_roundtrip(v, a, b):
    q = Quantity(v, a).convert_to(b)
    assert dimension_of(q.unit) == dimension_of(a)
    assert abs(q.convert_to(a).value - v) < Decimal("0.000001")


@given(xs=st.lists(st.integers(-10_000_000, 10_000_000), max_size=50))
def test_money_sum_is_exact(xs):
    total = Money.zero()
    for x in xs:
        total = total + Money(x)
    assert total.minor == sum(xs)
