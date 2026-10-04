"""Seed the demo dataset into a database (idempotent)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from hjemmefra.demo import dataset as D
from hjemmefra.jobs.ingestion_job import ingest_into_db
from hjemmefra.persistence import models as M
from hjemmefra.persistence.repositories import HouseholdRepo, PantryRepo, ProductRepo, RecipeRepo, StoreRepo


def seed_demo(s: Session, api_key: str = "demo-key") -> dict:
    sr = StoreRepo(s)
    for c in D.CHAINS:
        sr.upsert_chain(c)
    for st in D.STORES:
        sr.upsert(st)
    pr = ProductRepo(s)
    for p in D.PRODUCTS:
        pr.upsert(p)
    rr = RecipeRepo(s)
    for r in D.RECIPES:
        rr.upsert(r)
    if s.get(M.HouseholdRow, D.HOUSEHOLD.household_id) is None:
        HouseholdRepo(s).create(D.HOUSEHOLD.model_copy(deep=True), api_key)
        pantry = PantryRepo(s)
        for lot in D.PANTRY:
            pantry.add(lot)
    s.flush()
    summary = ingest_into_db(s, D.adapters(), D.NEGATIVE_ALIASES, now=D.CAPTURED_AT)
    return summary
