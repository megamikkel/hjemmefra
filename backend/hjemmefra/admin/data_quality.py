"""Admin data-quality helpers: review queue kinds and summary."""
from __future__ import annotations

from sqlalchemy.orm import Session

from hjemmefra.core.metrics import registry
from hjemmefra.persistence.repositories import ReviewRepo

REVIEW_KINDS = ["UNMATCHED_PRODUCT", "OFFER_SUSPICIOUS", "OFFER_INVALID", "OFFER_REQUIRES_REVIEW", "PARSE_FAILURE",
                "FAILED_IMPORT", "LOW_CONFIDENCE_MATCH", "UNKNOWN_UNIT", "DUPLICATE_CANDIDATE", "UNIT_CONVERSION_UNKNOWN"]


def summary(s: Session) -> dict:
    rq = ReviewRepo(s)
    open_items = rq.open()
    by_kind: dict[str, int] = {}
    for it in open_items:
        by_kind[it.kind] = by_kind.get(it.kind, 0) + 1
    return {"open_total": len(open_items), "open_by_kind": by_kind, "metrics": registry.snapshot()}
