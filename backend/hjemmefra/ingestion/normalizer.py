"""Raw record -> NormalizedOffer.

Deterministic parsing only. OCR values are never trusted blindly: an OCR price
goes through plausibility checks (requirement 8) and the resulting confidence is
carried on the offer. Missing prices stay None (UNKNOWN) - never invented.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple

from hjemmefra.core.confidence import Confidence
from hjemmefra.core.ids import stable_hash
from hjemmefra.core.units import UnknownUnit, parse_unit
from hjemmefra.domain.offer import NormalizedOffer, OcrField, RawOfferRecord, SourceType
from hjemmefra.domain.store import OfferScope

OCR_HIGH = 0.90
OCR_MEDIUM = 0.75


def _to_minor(value) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, float):
        raise TypeError("prices must not be floats")
    try:
        d = Decimal(str(value).replace(",", "."))
    except InvalidOperation:
        return None
    return int((d * 100).quantize(Decimal(1)))


def _parse_date(v) -> date:
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v))


def interpret_ocr_price(field: OcrField, plausible_min_minor: int = 100, plausible_max_minor: int = 100_000) -> Tuple[Optional[int], Confidence, str]:
    """Interpret an OCR price string. Returns (minor, confidence, note).

    '2995' with no separator is ambiguous: 2995 kr or 29,95 kr. We pick the
    interpretation inside the plausible range for a grocery item; if both or
    neither are plausible the price is not usable (UNKNOWN)."""
    raw = field.raw_value.strip().replace(" ", "")
    if field.normalized_value:
        minor = _to_minor(field.normalized_value)
        return minor, _ocr_conf(field.confidence), "ocr normalized by source"
    candidates = []
    if re.fullmatch(r"\d+[.,]\d{2}", raw):
        candidates.append(_to_minor(raw))
    elif re.fullmatch(r"\d+", raw):
        as_whole = int(raw) * 100
        as_split = int(raw)  # digits already minor units (29,95 -> 2995)
        for c in (as_whole, as_split):
            if plausible_min_minor <= c <= plausible_max_minor:
                candidates.append(c)
    else:
        return None, Confidence.UNKNOWN, f"ocr price '{raw}' unparseable"
    candidates = [c for c in candidates if c is not None]
    if len(candidates) == 1:
        conf = _ocr_conf(field.confidence)
        if len(raw) and re.fullmatch(r"\d+", raw):
            # ambiguous layout resolved by plausibility -> downgrade one level
            conf = Confidence.MEDIUM if conf == Confidence.HIGH else Confidence.LOW
        return candidates[0], conf, "ocr price interpreted by plausibility range"
    return None, Confidence.UNKNOWN, f"ocr price '{raw}' ambiguous or implausible"


def _ocr_conf(c: float) -> Confidence:
    if c >= OCR_HIGH:
        return Confidence.HIGH
    if c >= OCR_MEDIUM:
        return Confidence.MEDIUM
    return Confidence.LOW


def source_confidence(source_type: SourceType) -> Confidence:
    return {
        SourceType.OFFICIAL_API: Confidence.VERIFIED,
        SourceType.LICENSED_FEED: Confidence.VERIFIED,
        SourceType.MANUAL: Confidence.VERIFIED,
        SourceType.DEMO: Confidence.VERIFIED,
        SourceType.PUBLIC_PAGE: Confidence.HIGH,
        SourceType.USER_SUPPLIED: Confidence.MEDIUM,
        SourceType.PDF_LEAFLET: Confidence.MEDIUM,
        SourceType.IMAGE_OCR: Confidence.LOW,
        SourceType.OTHER: Confidence.LOW,
    }[source_type]


def fingerprint_for(retailer: str, scope: str, store_id: Optional[str], title: str, valid_from: date, valid_to: date,
                    offer_minor: Optional[int], multi_q: Optional[int], multi_minor: Optional[int], pkg: str) -> str:
    return stable_hash(retailer, scope, store_id or "", title.strip().lower(), valid_from.isoformat(), valid_to.isoformat(),
                       str(offer_minor), str(multi_q), str(multi_minor), pkg)


def normalize(raw: RawOfferRecord, now: Optional[datetime] = None) -> NormalizedOffer:
    p = raw.payload
    notes: list[str] = []
    conf = source_confidence(raw.source_type)

    # --- prices (OCR aware) ---------------------------------------------
    offer_minor = _to_minor(p.get("offer_price"))
    normal_minor = _to_minor(p.get("normal_price"))
    multi_minor = _to_minor(p.get("multi_buy_price"))
    if "offer_price" in raw.ocr_fields:
        ocr_minor, ocr_conf, note = interpret_ocr_price(raw.ocr_fields["offer_price"])
        notes.append(note)
        offer_minor = ocr_minor
        conf = min(conf, ocr_conf, key=lambda c: c.rank)
    if "normal_price" in raw.ocr_fields:
        ocr_minor, ocr_conf, note = interpret_ocr_price(raw.ocr_fields["normal_price"])
        notes.append("normal: " + note)
        normal_minor = ocr_minor
    if offer_minor is None and multi_minor is None:
        conf = Confidence.UNKNOWN
        notes.append("PRICE_UNKNOWN")

    # --- package -----------------------------------------------------------
    pkg_q = p.get("package_quantity")
    pkg_q = Decimal(str(pkg_q)) if pkg_q not in (None, "") else None
    pkg_u = None
    if p.get("package_unit"):
        try:
            pkg_u = parse_unit(str(p["package_unit"]))
        except UnknownUnit:
            notes.append(f"UNKNOWN_UNIT:{p['package_unit']}")
            pkg_q = None
    pkg_count = int(p.get("package_count") or 1)

    valid_from = _parse_date(p["valid_from"])
    valid_to = _parse_date(p["valid_to"])
    scope = OfferScope(p.get("scope") or "NATIONAL")
    title = str(p.get("title") or "").strip()
    fp = fingerprint_for(raw.retailer, scope.value, p.get("store_id"), title, valid_from, valid_to, offer_minor,
                         p.get("multi_buy_quantity"), multi_minor, f"{pkg_q}{pkg_u.value if pkg_u else ''}x{pkg_count}")

    return NormalizedOffer(
        offer_id=f"off_{fp[:16]}",
        raw_id=raw.raw_id,
        source_id=raw.source_id,
        source_type=raw.source_type,
        source_reference=raw.source_reference,
        captured_at=raw.captured_at,
        last_verified_at=now or raw.captured_at,
        retailer=raw.retailer,
        scope=scope,
        store_id=p.get("store_id"),
        region=p.get("region"),
        valid_from=valid_from,
        valid_to=valid_to,
        raw_title=title,
        canonical_product_id=p.get("canonical_product_id"),
        brand=p.get("brand"),
        variant=p.get("variant"),
        package_quantity=pkg_q,
        package_unit=pkg_u,
        package_count=pkg_count,
        currency=p.get("currency") or "DKK",
        normal_price_minor=normal_minor,
        offer_price_minor=offer_minor,
        multi_buy_quantity=p.get("multi_buy_quantity"),
        multi_buy_price_minor=multi_minor,
        minimum_quantity=p.get("minimum_quantity"),
        maximum_quantity=p.get("maximum_quantity"),
        member_only=bool(p.get("member_only", False)),
        required_membership=p.get("required_membership"),
        coupon_required=bool(p.get("coupon_required", False)),
        deposit_minor=_to_minor(p.get("deposit")) or 0,
        assortment_text=p.get("assortment_text"),
        conditions=p.get("conditions"),
        price_confidence=conf,
        validation_notes=notes,
        fingerprint=fp,
    )
