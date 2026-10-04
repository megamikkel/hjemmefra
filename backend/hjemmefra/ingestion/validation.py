"""Offer validation pipeline -> NORMAL / SUSPICIOUS / INVALID / REQUIRES_REVIEW.

Historical prices are used as a sanity check, never as a replacement for the
actual source price (requirement 7).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Callable, List, Optional, Sequence

from hjemmefra.core.confidence import Confidence
from hjemmefra.core.units import Quantity
from hjemmefra.domain.offer import NormalizedOffer, PriceObservation, ValidationStatus
from hjemmefra.domain.store import OfferScope

# Reasonable range for a single grocery line in DKK minor units.
PRICE_MIN_MINOR = 50  # 0.50 kr
PRICE_MAX_MINOR = 200_000  # 2000 kr
OUTLIER_RATIO_LOW = Decimal("0.35")  # < 35 % of historical median -> suspicious
OUTLIER_RATIO_HIGH = Decimal("3.0")


@dataclass
class ValidationResult:
    status: ValidationStatus
    reasons: List[str] = field(default_factory=list)


def unit_price_per_base(offer: NormalizedOffer) -> Optional[Decimal]:
    """Effective single-package price per base unit (øre/g, øre/ml, øre/stk)."""
    if offer.package_quantity is None or offer.package_unit is None:
        return None
    base_qty = Quantity(offer.package_quantity * offer.package_count, offer.package_unit).base_amount()
    if base_qty <= 0:
        return None
    price = offer.offer_price_minor
    if price is None and offer.multi_buy_quantity and offer.multi_buy_price_minor:
        price = Decimal(offer.multi_buy_price_minor) / offer.multi_buy_quantity
    if price is None:
        return None
    return (Decimal(price) / base_qty).quantize(Decimal("0.0001"))


def validate_offer(offer: NormalizedOffer, history: Sequence[PriceObservation] = (), today: Optional[date] = None,
                   known_store_ids: Optional[set[str]] = None) -> ValidationResult:
    reasons: List[str] = []
    invalid = False
    suspicious = False
    review = False

    if offer.valid_from > offer.valid_to:
        invalid = True
        reasons.append("valid_from > valid_to")
    if offer.currency != "DKK":
        review = True
        reasons.append(f"unexpected currency {offer.currency}")

    # price presence / positivity
    if offer.offer_price_minor is None and offer.multi_buy_price_minor is None:
        review = True
        reasons.append("PRICE_UNKNOWN")
    for name, v in (("offer_price", offer.offer_price_minor), ("normal_price", offer.normal_price_minor),
                    ("multi_buy_price", offer.multi_buy_price_minor)):
        if v is not None and v <= 0:
            invalid = True
            reasons.append(f"{name} <= 0")
        if v is not None and not (PRICE_MIN_MINOR <= v <= PRICE_MAX_MINOR):
            suspicious = True
            reasons.append(f"{name} outside plausible range")

    # quantity
    if offer.package_quantity is not None and offer.package_quantity <= 0:
        invalid = True
        reasons.append("package_quantity <= 0")
    if offer.package_quantity is None or offer.package_unit is None:
        review = True
        reasons.append("UNKNOWN_PACKAGE_SIZE")
    if offer.package_count < 1:
        invalid = True
        reasons.append("package_count < 1")

    # multi-buy consistency
    if (offer.multi_buy_quantity is None) != (offer.multi_buy_price_minor is None):
        invalid = True
        reasons.append("multi_buy quantity/price mismatch")
    if offer.multi_buy_quantity is not None:
        if offer.multi_buy_quantity < 2:
            invalid = True
            reasons.append("multi_buy_quantity < 2")
        if offer.offer_price_minor is not None and offer.multi_buy_price_minor is not None \
                and offer.multi_buy_price_minor > offer.offer_price_minor * offer.multi_buy_quantity:
            suspicious = True
            reasons.append("multi-buy price higher than buying singles")
    if offer.minimum_quantity is not None and offer.maximum_quantity is not None \
            and offer.minimum_quantity > offer.maximum_quantity:
        invalid = True
        reasons.append("minimum_quantity > maximum_quantity")

    # normal vs offer
    if offer.normal_price_minor is not None and offer.offer_price_minor is not None \
            and offer.normal_price_minor < offer.offer_price_minor:
        suspicious = True
        reasons.append("normal price lower than offer price")

    # store scope
    if offer.scope == OfferScope.STORE and not offer.store_id:
        invalid = True
        reasons.append("STORE scope without store_id")
    if offer.scope == OfferScope.STORE and known_store_ids is not None and offer.store_id not in known_store_ids:
        review = True
        reasons.append("store_id unknown")
    if offer.scope in (OfferScope.REGIONAL, OfferScope.LOCAL) and not offer.region:
        invalid = True
        reasons.append("regional scope without region")

    # membership
    if offer.member_only and not offer.required_membership:
        review = True
        reasons.append("member_only without required_membership program")
    if offer.deposit_minor < 0:
        invalid = True
        reasons.append("negative deposit")

    # confidence
    if offer.price_confidence in (Confidence.LOW, Confidence.UNKNOWN):
        review = True
        reasons.append(f"price_confidence {offer.price_confidence.value}")

    # historical sanity check
    up = unit_price_per_base(offer)
    hist = [h.unit_price_minor_per_base for h in history
            if offer.canonical_product_id and h.canonical_product_id == offer.canonical_product_id]
    if up is not None and len(hist) >= 3:
        s = sorted(hist)
        median = s[len(s) // 2]
        if median > 0:
            ratio = up / median
            if ratio < OUTLIER_RATIO_LOW or ratio > OUTLIER_RATIO_HIGH:
                suspicious = True
                reasons.append(f"unit price {up} deviates from historical median {median} (ratio {ratio:.2f})")

    if invalid:
        return ValidationResult(ValidationStatus.INVALID, reasons)
    if suspicious:
        return ValidationResult(ValidationStatus.SUSPICIOUS, reasons)
    if review:
        return ValidationResult(ValidationStatus.REQUIRES_REVIEW, reasons)
    return ValidationResult(ValidationStatus.NORMAL, reasons)


def usable_for_pricing(offer: NormalizedOffer, min_confidence: Confidence = Confidence.MEDIUM) -> bool:
    """An offer may feed exact-price plans only if validation passed and confidence is sufficient."""
    return offer.validation_status == ValidationStatus.NORMAL and offer.price_confidence.at_least(min_confidence) \
        and (offer.offer_price_minor is not None or offer.multi_buy_price_minor is not None) \
        and offer.package_quantity is not None and offer.package_unit is not None
