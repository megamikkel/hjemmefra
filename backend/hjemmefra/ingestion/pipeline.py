"""Ingestion orchestration: fetch -> normalize -> resolve -> validate -> dedupe.

Observable via metrics; tolerant to failing sources (coverage warnings)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

from hjemmefra.catalog.resolver import ProductResolver
from hjemmefra.core.confidence import MatchConfidence
from hjemmefra.core.logging import get_logger
from hjemmefra.core.metrics import OFFERS_DEDUPED, OFFERS_INGESTED, OFFERS_VALIDATION, PRODUCT_MATCH, SOURCE_FRESHNESS, registry
from hjemmefra.domain.offer import NormalizedOffer, PriceObservation, RawOfferRecord
from hjemmefra.ingestion.base import SourceAdapter
from hjemmefra.ingestion.dedup import deduplicate
from hjemmefra.ingestion.normalizer import normalize
from hjemmefra.ingestion.validation import validate_offer

log = get_logger(__name__)


@dataclass
class IngestionReport:
    raw_records: List[RawOfferRecord] = field(default_factory=list)
    offers: List[NormalizedOffer] = field(default_factory=list)
    duplicates: int = 0
    failed_sources: Dict[str, str] = field(default_factory=dict)
    review_queue: List[dict] = field(default_factory=list)

    @property
    def coverage_warnings(self) -> List[str]:
        return [f"Planen er beregnet uden data fra {sid}: {err}" for sid, err in self.failed_sources.items()]


def run_ingestion(adapters: Sequence[SourceAdapter], resolver: Optional[ProductResolver] = None,
                  history: Sequence[PriceObservation] = (), existing: Optional[Dict[str, NormalizedOffer]] = None,
                  known_store_ids: Optional[set[str]] = None, now: Optional[datetime] = None) -> IngestionReport:
    now = now or datetime.now(timezone.utc)
    report = IngestionReport()
    normalized: List[NormalizedOffer] = []
    for adapter in adapters:
        result = adapter.fetch()
        if not result.ok:
            report.failed_sources[adapter.descriptor.source_id] = result.error or "unknown error"
            log.warning("source_failed", source_id=adapter.descriptor.source_id, error=result.error)
            registry.inc("source_fetch_total", source=adapter.descriptor.source_id, status="failed")
            continue
        registry.inc("source_fetch_total", source=adapter.descriptor.source_id, status="ok")
        if result.captured_at:
            registry.observe(SOURCE_FRESHNESS, (now - result.captured_at).total_seconds(), source=adapter.descriptor.source_id)
        for raw in result.records:
            report.raw_records.append(raw)
            try:
                offer = normalize(raw, now=now)
            except Exception as exc:  # parsing failure -> review queue, do not abort
                registry.inc("offer_parse_failures_total", source=adapter.descriptor.source_id)
                report.review_queue.append({"type": "PARSE_FAILURE", "raw_id": raw.raw_id, "error": str(exc)})
                continue
            if resolver is not None:
                if offer.canonical_product_id and resolver.get(offer.canonical_product_id):
                    offer.match_confidence = MatchConfidence.HIGH  # pre-resolved by source/admin
                else:
                    match = resolver.resolve(offer.raw_title)
                    offer.canonical_product_id = match.canonical_id
                    offer.match_confidence = match.confidence
                    if match.confidence in (MatchConfidence.LOW, MatchConfidence.UNMATCHED):
                        report.review_queue.append({"type": "UNMATCHED_PRODUCT", "offer_id": offer.offer_id,
                                                    "title": offer.raw_title, "confidence": match.confidence.value})
                registry.inc(PRODUCT_MATCH, confidence=offer.match_confidence.value)
            v = validate_offer(offer, history=history, known_store_ids=known_store_ids)
            offer.validation_status = v.status
            offer.validation_notes.extend(v.reasons)
            registry.inc(OFFERS_VALIDATION, status=v.status.value)
            if v.status.value != "NORMAL":
                report.review_queue.append({"type": f"OFFER_{v.status.value}", "offer_id": offer.offer_id,
                                            "title": offer.raw_title, "reasons": v.reasons})
            normalized.append(offer)
    fresh, dups = deduplicate(normalized, existing)
    report.offers = fresh
    report.duplicates = len(dups)
    registry.inc(OFFERS_INGESTED, len(fresh))
    registry.inc(OFFERS_DEDUPED, len(dups))
    return report
