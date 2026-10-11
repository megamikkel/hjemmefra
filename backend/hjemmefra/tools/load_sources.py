"""Load files produced by fetch_sources into the database through the normal pipeline."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from sqlalchemy.orm import Session

from hjemmefra.catalog.resolver import ProductResolver
from hjemmefra.domain.store import Chain
from hjemmefra.ingestion.adapters.salling import SallingFoodWasteAdapter, fetch_salling_stores
from hjemmefra.ingestion.adapters.tjek import TjekOffersAdapter
from hjemmefra.ingestion.base import SourceAdapter
from hjemmefra.jobs.ingestion_job import ingest_into_db
from hjemmefra.location.geo import POSTAL_CENTROIDS
from hjemmefra.persistence.repositories import ProductRepo, RecipeRepo, ReviewRepo, StoreRepo
from hjemmefra.recipes.importer import recipe_from_jsonld


def _file_fetch(path: Path):
    data = json.loads(path.read_text())

    def fetch(url, headers, params):
        if "offset" in params:  # tjek pagination over a single stored list
            off, lim = params["offset"], params["limit"]
            return data[off:off + lim]
        return data
    return fetch


def load_dir(s: Session, data_dir: Path, zip_code: str, negative_aliases: dict | None = None) -> dict:
    manifest = json.loads((data_dir / "manifest.json").read_text()) if (data_dir / "manifest.json").exists() else {}
    fetched_at = datetime.fromisoformat(manifest["fetched_at"]) if manifest.get("fetched_at") else datetime.now(timezone.utc)
    summary: dict = {"manifest": manifest}
    adapters: List[SourceAdapter] = []
    p = data_dir / f"salling_food_waste_{zip_code}.json"
    if p.exists():
        adapters.append(SallingFoodWasteAdapter("file", zip_code, fetch=_file_fetch(p), now=fetched_at))
    p = data_dir / f"salling_stores_{zip_code}.json"
    if p.exists():
        repo = StoreRepo(s)
        stores = fetch_salling_stores("file", zip_code, fetch=_file_fetch(p))
        for chain in {st.chain_id for st in stores}:
            if not any(c.chain_id == chain for c in repo.chains()):
                repo.upsert_chain(Chain(chain_id=chain, name=chain.capitalize(), membership_program_id="salling_plus"))
        for st in stores:
            repo.upsert(st)
        summary["stores"] = len(stores)
    p = data_dir / f"tjek_offers_{zip_code}.json"
    if p.exists() and zip_code in POSTAL_CENTROIDS:
        lat, lon = POSTAL_CENTROIDS[zip_code]
        adapters.append(TjekOffersAdapter("file", lat, lon, 10000, zip_code, fetch=_file_fetch(p), now=fetched_at))
    if adapters:
        summary["offers"] = ingest_into_db(s, adapters, negative_aliases, now=fetched_at)
    resolver = ProductResolver(ProductRepo(s).all(), negative_aliases)
    rr, rq = RecipeRepo(s), ReviewRepo(s)
    recipes = []
    for f in sorted((data_dir / "recipes").glob("*.json")) if (data_dir / "recipes").exists() else []:
        doc = json.loads(f.read_text())
        res = recipe_from_jsonld(doc["recipe"], doc["url"], resolver)
        if res.recipe:
            rr.upsert(res.recipe)
            for item in res.review_items:
                rq.add(item["type"], {**item, "recipe_id": res.recipe.recipe_id})
            recipes.append({"recipe_id": res.recipe.recipe_id, "name": res.recipe.name, "review_required": res.recipe.review_required,
                            "review_items": len(res.review_items)})
    summary["recipes"] = recipes
    return summary
