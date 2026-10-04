from datetime import date, datetime, timezone
from decimal import Decimal

from hjemmefra.catalog.resolver import ProductResolver
from hjemmefra.core.confidence import Confidence
from hjemmefra.demo.dataset import CAPTURED_AT, PRODUCTS, RAW_OFFERS, SOURCES, adapters
from hjemmefra.domain.offer import OcrField, PriceObservation, SourceType, ValidationStatus
from hjemmefra.ingestion.adapters.failing import FailingAdapter
from hjemmefra.ingestion.adapters.manual_json import ManualJsonAdapter
from hjemmefra.ingestion.base import ComplianceClass, SourceDescriptor
from hjemmefra.ingestion.normalizer import interpret_ocr_price, normalize
from hjemmefra.ingestion.pipeline import run_ingestion
from hjemmefra.ingestion.validation import usable_for_pricing, validate_offer

NOW = datetime(2026, 10, 4, tzinfo=timezone.utc)
DESC = SourceDescriptor("t", SourceType.IMAGE_OCR, ComplianceClass.USER_SUPPLIED, "netto")


def rec(**kw):
    d = {"external_id": "e1", "title": "Laksefilet 400 g", "valid_from": "2026-10-05", "valid_to": "2026-10-11",
         "package_quantity": "400", "package_unit": "g", "normal_price": "69.00", "offer_price": "39.00"}
    d.update(kw)
    return d


def norm(record, desc=DESC):
    res = ManualJsonAdapter(desc, records=[record], captured_at=NOW).fetch()
    return normalize(res.records[0], now=NOW)


def test_ocr_2995_interpreted_as_29_95_with_downgraded_confidence():
    minor, conf, _ = interpret_ocr_price(OcrField(raw_value="2995", confidence=0.95))
    assert minor == 2995 and conf == Confidence.MEDIUM


def test_ocr_ambiguous_price_is_unknown():
    # 150 -> 150 kr or 1,50 kr: both plausible -> UNKNOWN
    minor, conf, _ = interpret_ocr_price(OcrField(raw_value="150", confidence=0.95))
    assert minor is None and conf == Confidence.UNKNOWN


def test_low_confidence_ocr_offer_not_usable_for_pricing():
    o = norm(rec(ocr={"offer_price": {"raw_value": "3900", "confidence": 0.55}}))
    o.validation_status = validate_offer(o).status
    assert o.price_confidence == Confidence.LOW
    assert o.validation_status == ValidationStatus.REQUIRES_REVIEW
    assert not usable_for_pricing(o)


def test_missing_price_is_unknown_not_invented():
    o = norm(rec(offer_price=None, normal_price=None))
    assert o.offer_price_minor is None and o.price_confidence == Confidence.UNKNOWN
    assert "PRICE_UNKNOWN" in validate_offer(o).reasons


def test_invalid_dates_and_multibuy():
    o = norm(rec(valid_from="2026-10-12"))
    assert validate_offer(o).status == ValidationStatus.INVALID
    o = norm(rec(multi_buy_quantity=2))  # price missing
    assert validate_offer(o).status == ValidationStatus.INVALID


def test_store_scope_requires_store_id():
    o = norm(rec(scope="STORE"))
    assert validate_offer(o).status == ValidationStatus.INVALID


def test_unknown_unit_goes_to_review():
    o = norm(rec(package_unit="bundt"))
    assert o.package_quantity is None and any(n.startswith("UNKNOWN_UNIT") for n in o.validation_notes)
    assert validate_offer(o).status == ValidationStatus.REQUIRES_REVIEW


def test_extreme_outlier_vs_history_is_suspicious():
    o = norm(rec(offer_price="3.00", canonical_product_id="SALMON_FILLET"))
    hist = [PriceObservation(canonical_product_id="SALMON_FILLET", retailer="x", observed_on=date(2026, 9, d),
                             unit_price_minor_per_base=Decimal("15"), is_offer=False, source_id="s", confidence=Confidence.HIGH) for d in (1, 2, 3)]
    r = validate_offer(o, history=hist)
    assert r.status == ValidationStatus.SUSPICIOUS


def test_duplicate_offer_is_idempotent():
    resolver = ProductResolver(PRODUCTS)
    first = run_ingestion(adapters(), resolver=resolver, now=NOW)
    existing = {o.fingerprint: o for o in first.offers}
    second = run_ingestion(adapters(), resolver=resolver, existing=existing, now=NOW)
    assert len(first.offers) == len(RAW_OFFERS) and second.offers == [] and second.duplicates == len(RAW_OFFERS)


def test_failing_source_degrades_gracefully():
    bad = FailingAdapter(SourceDescriptor("broken", SourceType.OFFICIAL_API, ComplianceClass.OFFICIAL_API, "coop"), "timeout")
    report = run_ingestion([bad, *adapters()], resolver=ProductResolver(PRODUCTS), now=NOW)
    assert "broken" in report.failed_sources and len(report.offers) == len(RAW_OFFERS)
    assert any("broken" in w for w in report.coverage_warnings)


def test_provenance_preserved():
    report = run_ingestion(adapters(), resolver=ProductResolver(PRODUCTS), now=NOW)
    o = report.offers[0]
    raw = next(r for r in report.raw_records if r.raw_id == o.raw_id)
    assert raw.payload["title"] == o.raw_title and o.source_id == raw.source_id and o.captured_at == CAPTURED_AT
