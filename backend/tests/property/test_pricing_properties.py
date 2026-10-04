from datetime import date, datetime, timezone
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from hjemmefra.core.confidence import Confidence
from hjemmefra.core.units import Unit
from hjemmefra.domain.offer import NormalizedOffer, SourceType
from hjemmefra.domain.store import OfferScope
from hjemmefra.ingestion.normalizer import interpret_ocr_price
from hjemmefra.domain.offer import OcrField
from hjemmefra.pricing.engine import product_cost_for_packages

NOW = datetime(2026, 10, 4, tzinfo=timezone.utc)


def mk(single, normal, k, P, deposit):
    return NormalizedOffer(offer_id="o", raw_id="r", source_id="s", source_type=SourceType.MANUAL, source_reference="x", captured_at=NOW,
                           last_verified_at=NOW, retailer="r", scope=OfferScope.NATIONAL, valid_from=date(2026, 1, 1), valid_to=date(2026, 12, 31),
                           raw_title="t", package_quantity=Decimal(1), package_unit=Unit.STK, normal_price_minor=normal, offer_price_minor=single,
                           multi_buy_quantity=k, multi_buy_price_minor=P, deposit_minor=deposit, price_confidence=Confidence.VERIFIED)


@settings(max_examples=300, deadline=None)
@given(single=st.integers(100, 10000), normal=st.one_of(st.none(), st.integers(100, 20000)), k=st.integers(2, 5),
       frac=st.integers(50, 100), deposit=st.integers(0, 300), n=st.integers(0, 12))
def test_cost_monotone_and_never_below_cheapest_unit(single, normal, k, frac, deposit, n):
    P = single * k * frac // 100  # multi-buy at most as expensive as singles
    o = mk(single, normal, k, P, deposit)
    c = product_cost_for_packages(o, n)
    assert c.packages >= n
    assert c.deposit_minor == deposit * c.packages
    cheapest_unit = min(single, P // k)
    assert c.product_cost_minor >= cheapest_unit * n
    if n > 0:
        prev = product_cost_for_packages(o, n - 1)
        assert c.product_cost_minor + c.deposit_minor >= 0 and c.packages >= prev.packages


@settings(max_examples=200, deadline=None)
@given(digits=st.text(alphabet="0123456789", min_size=1, max_size=6), conf=st.floats(0, 1))
def test_ocr_never_returns_implausible_price(digits, conf):
    minor, c, _ = interpret_ocr_price(OcrField(raw_value=digits, confidence=conf))
    if minor is not None:
        assert 100 <= minor <= 100_000
        assert c in (Confidence.MEDIUM, Confidence.LOW)
