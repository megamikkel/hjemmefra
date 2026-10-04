from __future__ import annotations

from datetime import timedelta

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from hjemmefra.admin.data_quality import REVIEW_KINDS, summary
from hjemmefra.api.deps import get_session, require_admin
from hjemmefra.api.schemas import OfferImport, ReviewResolve
from hjemmefra.core.errors import NotFound
from hjemmefra.core.metrics import registry
from hjemmefra.domain.offer import SourceType
from hjemmefra.ingestion.adapters.manual_json import ManualJsonAdapter
from hjemmefra.ingestion.base import ComplianceClass, SourceDescriptor
from hjemmefra.catalog.resolver import ProductResolver
from hjemmefra.config import Settings
from hjemmefra.domain.store import Chain
from hjemmefra.ingestion.adapters.salling import fetch_salling_stores
from hjemmefra.ingestion.base import SourceUnavailable
from hjemmefra.ingestion.sources import configured_adapters
from hjemmefra.jobs.ingestion_job import ingest_into_db
from hjemmefra.recipes.importer import import_recipe_from_url
from hjemmefra.jobs.runner import run_job
from hjemmefra.persistence.repositories import JobRepo, OfferRepo, ProductRepo, RecipeRepo, ReviewRepo, StoreRepo

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


class RecipeImportBody(BaseModel):
    urls: List[str]


class SourceRunBody(BaseModel):
    postal_code: Optional[str] = None


@router.post("/ingestion/run")
def run_configured_sources(body: SourceRunBody, request: Request, s: Session = Depends(get_session)):
    """Fetch all configured live sources (Salling Group API, Tjek API) through the validation pipeline."""
    cfg: Settings = request.app.state.settings
    adapters = configured_adapters(cfg, body.postal_code)
    if not adapters:
        raise HTTPException(400, "no live sources configured: set HJEMMEFRA_SALLING_API_TOKEN / HJEMMEFRA_TJEK_API_KEY and a postal code")
    result = run_job("live_ingestion", lambda: ingest_into_db(s, adapters), max_attempts=2)
    JobRepo(s).record(result.job_name, result.status, result.attempts, result.started_at, result.finished_at, result.error, result.summary)
    if result.status != "SUCCEEDED":
        raise HTTPException(502, result.error)
    return {"sources": [a.descriptor.source_id for a in adapters], **(result.summary or {})}


@router.post("/stores/import-salling")
def import_salling_stores(body: SourceRunBody, request: Request, s: Session = Depends(get_session)):
    cfg: Settings = request.app.state.settings
    postal = body.postal_code or cfg.source_postal_code
    if not cfg.salling_api_token or not postal:
        raise HTTPException(400, "HJEMMEFRA_SALLING_API_TOKEN and a postal code are required")
    try:
        stores = fetch_salling_stores(cfg.salling_api_token, postal)
    except SourceUnavailable as exc:
        raise HTTPException(502, str(exc))
    repo = StoreRepo(s)
    for chain in {st.chain_id for st in stores}:
        if not any(c.chain_id == chain for c in repo.chains()):
            repo.upsert_chain(Chain(chain_id=chain, name=chain.capitalize(), membership_program_id="salling_plus"))
    for st in stores:
        repo.upsert(st)
    return {"imported": len(stores), "store_ids": [st.store_id for st in stores]}


@router.post("/recipes/import")
def import_recipes(body: RecipeImportBody, s: Session = Depends(get_session)):
    """Import recipes from pages publishing schema.org/Recipe JSON-LD. Unresolved ingredients go to the review queue."""
    resolver = ProductResolver(ProductRepo(s).all())
    rr, rq = RecipeRepo(s), ReviewRepo(s)
    out = []
    for url in body.urls[:20]:
        res = import_recipe_from_url(url, resolver)
        if res.recipe is None:
            rq.add("FAILED_IMPORT", {"source": url, "error": res.error})
            out.append({"url": url, "status": "FAILED", "error": res.error})
            continue
        rr.upsert(res.recipe)
        for item in res.review_items:
            rq.add(item["type"], {**item, "recipe_id": res.recipe.recipe_id})
        out.append({"url": url, "status": "REVIEW_REQUIRED" if res.recipe.review_required else "OK",
                    "recipe_id": res.recipe.recipe_id, "name": res.recipe.name, "ingredients": len(res.recipe.ingredients),
                    "review_items": len(res.review_items)})
    return out


@router.get("/metrics")
def metrics():
    return registry.snapshot()
