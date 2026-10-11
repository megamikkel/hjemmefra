from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from hjemmefra.core.confidence import Confidence
from hjemmefra.core.units import Quantity, Unit, UnitConversionUnknown
from hjemmefra.domain.household import Household, HouseholdMember, Location, Membership
from hjemmefra.domain.offer import NormalizedOffer, PriceObservation, SourceType
from hjemmefra.domain.store import OfferScope
from hjemmefra.pricing.engine import (PriceUnavailable, consumed_value, eligibility, packages_needed,
                                      product_cost_for_packages, reference_price)

NOW = datetime(2026, 10, 4, tzinfo=timezone.utc)


def offer(**kw) -> NormalizedOffer:
    base = dict(offer_id="o", raw_id="r", source_id="s", source_type=SourceType.MANUAL, source_reference="x", captured_at=NOW,
                last_verified_at=NOW, retailer="rema", scope=OfferScope.NATIONAL, valid_from=date(2026, 10, 5), valid_to=date(2026, 10, 11),
                raw_title="t", canonical_product_id="X", package_quantity=Decimal(500), package_unit=Unit.G,
                normal_price_minor=3000, offer_price_minor=2500, price_confidence=Confidence.VERIFIED)
    base.update(kw)
    return NormalizedOffer(**base)


def hh(memberships=()):
    return Household(household_id="h", name="h", members=[HouseholdMember()], location=Location(postal_code="8000"),
                     memberships=list(memberships))


def test_two_for_fifty_when_only_one_needed_costs_fifty():
    o = offer(offer_price_minor=None, multi_buy_quantity=2, multi_buy_price_minor=5000, normal_price_minor=None)
    c = product_cost_for_packages(o, 1)
    assert c.packages == 2 and c.product_cost_minor == 5000 and c.multi_buy_applied


def test_two_for_fifty_remainder_at_normal_price_when_known():
    o = offer(offer_price_minor=None, multi_buy_quantity=2, multi_buy_price_minor=5000, normal_price_minor=3000)
    c = product_cost_for_packages(o, 3)
    assert c.packages == 3 and c.product_cost_minor == 8000


def test_three_for_hundred_multiple_groups():
    o = offer(offer_price_minor=None, multi_buy_quantity=3, multi_buy_price_minor=10000, normal_price_minor=4000)
    assert product_cost_for_packages(o, 6).product_cost_minor == 20000
    assert product_cost_for_packages(o, 7).product_cost_minor == 24000


def test_minimum_quantity_rule():
    o = offer(offer_price_minor=2500, minimum_quantity=3, normal_price_minor=3000)
    assert product_cost_for_packages(o, 2).product_cost_minor == 6000  # normal price below minimum
    assert product_cost_for_packages(o, 3).product_cost_minor == 7500


def test_maximum_quantity_rule():
    o = offer(offer_price_minor=2500, maximum_quantity=2, normal_price_minor=3000)
    assert product_cost_for_packages(o, 3).product_cost_minor == 2 * 2500 + 3000
    with pytest.raises(PriceUnavailable):
        product_cost_for_packages(offer(offer_price_minor=2500, maximum_quantity=2, normal_price_minor=None), 3)


def test_deposit_separate_from_product_cost():
    o = offer(deposit_minor=150)
    c = product_cost_for_packages(o, 2)
    assert c.product_cost_minor == 5000 and c.deposit_minor == 300 and c.checkout_minor == 5300


def test_price_unknown_never_invented():
    with pytest.raises(PriceUnavailable):
        product_cost_for_packages(offer(offer_price_minor=None, normal_price_minor=None), 1)


def test_membership_eligibility():
    o = offer(member_only=True, required_membership="lidl_plus")
    assert eligibility(o, hh()) == "MEMBERSHIP_REQUIRED:lidl_plus"
    assert eligibility(o, hh([Membership(program_id="lidl_plus")])) is None
    c = offer(coupon_required=True, required_membership="coop")
    assert eligibility(c, hh([Membership(program_id="coop")])) == "COUPON_REQUIRED:coop"
    assert eligibility(c, hh([Membership(program_id="coop", has_digital_coupons=True)])) is None


def test_packages_needed_and_package_economics():
    o = offer(package_quantity=Decimal(1000), offer_price_minor=6000)
    assert packages_needed(Quantity(Decimal(300), Unit.G), o) == 1
    c = product_cost_for_packages(o, 1)
    assert c.checkout_minor == 6000  # not 18 kr
    assert consumed_value(6000, Decimal(1000), Decimal(300)) == 1800
    with pytest.raises(UnitConversionUnknown):
        packages_needed(Quantity(Decimal(500), Unit.ML), o)


def test_reference_price_methods():
    assert reference_price(offer(), [])[1] == "OFFER_STATED_NORMAL"
    o = offer(normal_price_minor=None)
    assert reference_price(o, [])[1:] == ("UNKNOWN", Confidence.UNKNOWN)
    hist = [PriceObservation(canonical_product_id="X", retailer="rema", observed_on=date(2026, 9, d), unit_price_minor_per_base=Decimal("6"),
                             is_offer=False, source_id="s", confidence=Confidence.HIGH) for d in (1, 8, 15)]
    ref, method, conf = reference_price(o, hist)
    assert (ref, method, conf) == (3000, "HISTORICAL_MEDIAN", Confidence.MEDIUM)
