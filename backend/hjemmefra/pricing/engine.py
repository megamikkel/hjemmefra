"""Deterministic pricing engine.

Computes the real checkout cost for buying `n` packages under an offer's rules
(multi-buy, min/max quantity, member-only, coupon, deposit) and the package
economics (CHECKOUT_COST vs CONSUMED_VALUE). Never estimates a missing price.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional, Sequence

from hjemmefra.core.confidence import Confidence
from hjemmefra.core.units import Quantity, Unit, UnitConversionUnknown, compatible
from hjemmefra.domain.household import Household
from hjemmefra.domain.offer import NormalizedOffer, PriceObservation


class PriceUnavailable(Exception):
    """The offer cannot be priced (no price, unknown package, missing membership...)."""


@dataclass(frozen=True)
class PackageCost:
    packages: int
    product_cost_minor: int
    deposit_minor: int
    multi_buy_applied: bool

    @property
    def checkout_minor(self) -> int:
        return self.product_cost_minor + self.deposit_minor


def eligibility(offer: NormalizedOffer, household: Household) -> Optional[str]:
    """Return None if the household may use this price, else the blocking reason."""
    if offer.member_only or offer.required_membership:
        prog = offer.required_membership or offer.retailer
        if not household.has_membership(prog):
            return f"MEMBERSHIP_REQUIRED:{prog}"
    if offer.coupon_required:
        prog = offer.required_membership or offer.retailer
        if not household.has_coupons(prog):
            return f"COUPON_REQUIRED:{prog}"
    return None


def product_cost_for_packages(offer: NormalizedOffer, n: int) -> PackageCost:
    """Exact product cost (excl. deposit) for n packages following the offer rules.

    Rules:
    - multi-buy 'k for P': floor(n/k)*P; remainder packages priced at single
      offer price if stated, else at normal price if stated, else the multi-buy
      must be bought in full groups (round n up to a multiple of k). The
      extra packages become projected inventory.
    - minimum_quantity: below the minimum the offer price does not apply ->
      normal price if known, else the minimum must be bought.
    - maximum_quantity: packages above the max are priced at normal price if
      known; otherwise capped (caller must not exceed).
    """
    if n <= 0:
        return PackageCost(0, 0, 0, False)
    normal = offer.normal_price_minor
    single = offer.offer_price_minor
    k, P = offer.multi_buy_quantity, offer.multi_buy_price_minor
    mn, mx = offer.minimum_quantity, offer.maximum_quantity

    if single is None and P is None:
        raise PriceUnavailable("PRICE_UNKNOWN")

    eff_n = n
    if mn is not None and n < mn:
        if normal is not None:
            cost = normal * n
            return PackageCost(n, cost, offer.deposit_minor * n, False)
        eff_n = mn  # must buy the minimum to get the price at all

    offer_units = eff_n
    extra_units = 0
    if mx is not None and eff_n > mx:
        offer_units = mx
        extra_units = eff_n - mx
        if normal is None:
            raise PriceUnavailable("MAX_QUANTITY_EXCEEDED_NO_NORMAL_PRICE")

    cost = 0
    applied = False
    if k and P:
        groups, rem = divmod(offer_units, k)
        cost += groups * P
        applied = groups > 0
        if rem:
            if single is not None:
                cost += rem * single
            elif normal is not None:
                cost += rem * normal
            else:
                # must buy a whole extra group
                cost += P
                eff_n += k - rem
                applied = True
    else:
        cost += offer_units * single  # type: ignore[operator]
    cost += extra_units * (normal or 0)
    return PackageCost(eff_n, cost, offer.deposit_minor * eff_n, applied)


def cost_table(offer: NormalizedOffer, max_packages: int) -> List[PackageCost]:
    """Cost for 0..max_packages packages, used by the optimizer (element constraint).
    Entry i refers to *requesting* i packages; .packages may be larger if rules force it."""
    return [product_cost_for_packages(offer, i) for i in range(max_packages + 1)]


def packages_needed(required: Quantity, offer: NormalizedOffer, density: Optional[Decimal] = None) -> int:
    """Smallest number of packages whose total quantity covers `required`."""
    if offer.package_quantity is None or offer.package_unit is None:
        raise PriceUnavailable("UNKNOWN_PACKAGE_SIZE")
    pkg = Quantity(offer.package_quantity * offer.package_count, offer.package_unit)
    if not compatible(required.unit, pkg.unit):
        if density is None:
            raise UnitConversionUnknown(f"{required.unit.value} vs {pkg.unit.value}")
        required = required.convert_to(pkg.unit, density)
    need = required.base_amount()
    per = pkg.base_amount()
    n = int((need / per).to_integral_value(rounding="ROUND_CEILING"))
    return max(n, 1) if need > 0 else 0


def reference_price(offer: NormalizedOffer, history: Sequence[PriceObservation]) -> tuple[Optional[int], str, Confidence]:
    """Reference ('normal') price per package and the method used.

    Method precedence: OFFER_STATED_NORMAL (from the source) -> HISTORICAL_MEDIAN of
    verified non-offer observations (>=3 points) -> UNKNOWN."""
    if offer.normal_price_minor is not None:
        return offer.normal_price_minor, "OFFER_STATED_NORMAL", min(offer.price_confidence, Confidence.HIGH, key=lambda c: c.rank)
    pts = sorted(h.unit_price_minor_per_base for h in history
                 if h.canonical_product_id == offer.canonical_product_id and not h.is_offer
                 and h.confidence.at_least(Confidence.HIGH))
    if len(pts) >= 3 and offer.package_quantity is not None and offer.package_unit is not None:
        median = pts[len(pts) // 2]
        base = Quantity(offer.package_quantity * offer.package_count, offer.package_unit).base_amount()
        return int((median * base).quantize(Decimal(1), rounding=ROUND_HALF_UP)), "HISTORICAL_MEDIAN", Confidence.MEDIUM
    return None, "UNKNOWN", Confidence.UNKNOWN


def consumed_value(product_cost_minor: int, total_qty_base: Decimal, consumed_qty_base: Decimal) -> int:
    if total_qty_base <= 0:
        return 0
    share = min(Decimal(1), consumed_qty_base / total_qty_base)
    return int((Decimal(product_cost_minor) * share).quantize(Decimal(1), rounding=ROUND_HALF_UP))
