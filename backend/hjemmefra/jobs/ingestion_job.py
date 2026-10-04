"""Scheduled ingestion: fetch all sources, normalize, validate, dedupe, persist, fill review queue."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy.orm import Session

from hjemmefra.catalog.resolver import ProductResolver
from hjemmefra.ingestion.base import SourceAdapter
from hjemmefra.ingestion.pipeline import run_ingestion
from hjemmefra.persistence.repositories import OfferRepo, ProductRepo, ReviewRepo, StoreRepo


def ingest_into_db(s: Session, adapters: Sequence[SourceAdapter], negative_aliases: dict | None = None, now: datetime | None = None) -> dict:
    products = ProductRepo(s).all()
    resolver = ProductResolver(products, negative_aliases)
    offers_repo = OfferRepo(s)
    report = run_ingestion(adapters, resolver=resolver, history=offers_repo.observations(),
                           existing=offers_repo.existing_by_fingerprint(),
                           known_store_ids={st.store_id for st in StoreRepo(s).all()}, now=now or datetime.now(timezone.utc))
    offers_repo.store_raw(report.raw_records)
    new = offers_repo.upsert(report.offers)
    rq = ReviewRepo(s)
    for item in report.review_queue:
        rq.add(item["type"], item)
    for sid, err in report.failed_sources.items():
        rq.add("FAILED_IMPORT", {"source_id": sid, "error": err})
    return {"new_offers": new, "duplicates": report.duplicates, "review_items": len(report.review_queue),
            "failed_sources": report.failed_sources}
