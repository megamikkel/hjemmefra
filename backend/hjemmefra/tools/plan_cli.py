"""Build a plan from fetched data only (no demo prices).

  python -m hjemmefra.tools.plan_cli --data <fetched dir> --household household.json

Stores: when no store catalog is loaded for the postal code, one store per chain with offers
is created at the postal-code centroid and labelled UNVERIFIED (offers used are national, so
only the travel estimate depends on it).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from hjemmefra.catalog.base_catalog import merged_catalog
from hjemmefra.demo.dataset import NEGATIVE_ALIASES, PRODUCTS as DEMO_CATALOG
from hjemmefra.domain.household import Household
from hjemmefra.domain.pantry import InventoryLot
from hjemmefra.domain.plan import PlanRequest
from hjemmefra.domain.store import Chain, Store
from hjemmefra.location.geo import POSTAL_CENTROIDS
from hjemmefra.persistence.db import Base, make_engine, make_session_factory
from hjemmefra.persistence.repositories import OfferRepo, ProductRepo, RecipeRepo, StoreRepo
from hjemmefra.planning.service import PlanningData, generate_plan
from hjemmefra.tools.load_sources import load_dir

CHAIN_NAMES = {"lidl": "Lidl", "rema": "REMA 1000", "netto": "Netto", "bilka": "Bilka", "foetex": "føtex"}


def build(data_dir: Path, cfg: dict):
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = make_session_factory(engine)()
    pr = ProductRepo(s)
    for p in merged_catalog(DEMO_CATALOG):  # catalog only: canonical products, no prices
        pr.upsert(p)
    s.flush()
    summary = load_dir(s, data_dir, cfg["location"]["postal_code"], NEGATIVE_ALIASES)
    s.flush()
    offers = OfferRepo(s).all()
    stores = StoreRepo(s).all()
    postal = cfg["location"]["postal_code"]
    if not stores:
        lat, lon = POSTAL_CENTROIDS[postal]
        sr = StoreRepo(s)
        for chain in sorted({o.retailer for o in offers}):
            sr.upsert_chain(Chain(chain_id=chain, name=CHAIN_NAMES.get(chain, chain)))
            st = Store(store_id=f"{chain}_{postal}_unverified", chain_id=chain, postal_code=postal, lat=lat, lon=lon,
                       name=f"{CHAIN_NAMES.get(chain, chain)} ({postal}, butik ikke verificeret)")
            sr.upsert(st)
            stores.append(st)
    return s, summary, offers, stores


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--household", required=True)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    cfg = json.loads(Path(a.household).read_text())
    s, summary, offers, stores = build(Path(a.data), cfg)
    hh = Household.model_validate({k: cfg[k] for k in ("household_id", "name", "members", "location", "preferences", "memberships")})
    lots = [InventoryLot.model_validate({**l, "household_id": hh.household_id}) for l in cfg.get("pantry", [])]
    req = PlanRequest.model_validate({"household_id": hh.household_id, **cfg["request"]})
    data = PlanningData(household=hh, stores=stores, offers=offers, products={p.canonical_id: p for p in ProductRepo(s).all()},
                        recipes=[r for r in RecipeRepo(s).all()], pantry_lots=lots, pantry_version=1)
    plan = generate_plan(req, data)
    out = json.loads(plan.model_dump_json())
    out["_load_summary"] = summary
    if a.out:
        Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps({"offers": len(offers), "recipes": len(data.recipes), "stores": [st.name for st in stores]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
