from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from hjemmefra.admin.data_quality import REVIEW_KINDS, summary
from hjemmefra.api.deps import get_session, require_admin
from hjemmefra.api.schemas import OfferImport, ReviewResolve
from hjemmefra.core.errors import NotFound
from hjemmefra.core.metrics import registry
from hjemmefra.domain.offer import SourceType
from hjemmefra.ingestion.adapters.manual_json import ManualJsonAdapter
from hjemmefra.ingestion.base import ComplianceClass, SourceDescriptor
from hjemmefra.jobs.ingestion_job import ingest_into_db
from hjemmefra.jobs.runner import run_job
from hjemmefra.persistence.repositories import JobRepo, OfferRepo, ReviewRepo

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/data-quality")
def data_quality(s: Session = Depends(get_session)):
    return summary(s)


@router.get("/data-quality/review-queue")
def review_queue(kind: str | None = None, s: Session = Depends(get_session)):
    if kind and kind not in REVIEW_KINDS:
        raise HTTPException(400, f"unknown kind; one of {REVIEW_KINDS}")
    return [{"id": r.id, "kind": r.kind, "created_at": r.created_at, "payload": r.payload} for r in ReviewRepo(s).open(kind)]


@router.post("/data-quality/review-queue/{item_id}/resolve")
def resolve(item_id: int, body: ReviewResolve, s: Session = Depends(get_session)):
    rq = ReviewRepo(s)
    try:
        rq.resolve(item_id, body.model_dump())
    except NotFound:
        raise HTTPException(404, "item not found")
    if body.action == "MAP_PRODUCT" and body.canonical_product_id:
        item = s.get(__import__("hjemmefra.persistence.models", fromlist=["ReviewItemRow"]).ReviewItemRow, item_id)
        oid = (item.payload or {}).get("offer_id")
        if oid:
            repo = OfferRepo(s)
            o = repo.get(oid)
            o.canonical_product_id = body.canonical_product_id
            from hjemmefra.core.confidence import MatchConfidence
            o.match_confidence = MatchConfidence.HIGH
            repo.upsert([o])
    return {"status": "RESOLVED"}


@router.post("/offers/import")
def import_offers(body: OfferImport, s: Session = Depends(get_session)):
    """Manual / user-supplied import; runs the full validation pipeline and is idempotent."""
    desc = SourceDescriptor(source_id=body.source_id, source_type=SourceType(body.source_type),
                            compliance=ComplianceClass(body.compliance), retailer=body.retailer, freshness_sla=timedelta(days=7))
    adapter = ManualJsonAdapter(desc, records=body.records)
    result = run_job("manual_import", lambda: ingest_into_db(s, [adapter]), max_attempts=1)
    JobRepo(s).record(result.job_name, result.status, result.attempts, result.started_at, result.finished_at, result.error, result.summary)
    if result.status != "SUCCEEDED":
        raise HTTPException(500, result.error)
    return result.summary


@router.get("/metrics")
def metrics():
    return registry.snapshot()
