"""Fetch raw source data into files (run where network access exists, e.g. GitHub Actions).

Writes:
  <out>/salling_food_waste_<zip>.json   raw API response (if HJEMMEFRA_SALLING_API_TOKEN set)
  <out>/salling_stores_<zip>.json
  <out>/tjek_offers_<zip>.json          raw concatenated pages (if HJEMMEFRA_TJEK_API_KEY set)
  <out>/recipes/<hash>.json             schema.org Recipe JSON-LD node + source url
  <out>/manifest.json                   what was fetched, when, and what failed
The backend ingests these with `hjemmefra.tools.load_sources` through the normal pipeline,
so provenance, validation and confidence are identical to a live fetch.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from hjemmefra.core.ids import stable_hash
from hjemmefra.ingestion.adapters.salling import BASE as SALLING_BASE
from hjemmefra.ingestion.adapters.tjek import BASE as TJEK_BASE
from hjemmefra.ingestion.http import http_get_json, http_get_text
from hjemmefra.location.geo import POSTAL_CENTROIDS
from hjemmefra.recipes.importer import _LD, _find_recipe_node


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--zip", default=os.environ.get("HJEMMEFRA_SOURCE_POSTAL_CODE", ""))
    ap.add_argument("--radius", type=int, default=10000)
    ap.add_argument("--recipe-urls", help="text file with one URL per line")
    a = ap.parse_args(argv)
    out = Path(a.out)
    (out / "recipes").mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    manifest = {"fetched_at": now, "zip": a.zip, "ok": [], "failed": {}}

    tok = os.environ.get("HJEMMEFRA_SALLING_API_TOKEN", "")
    if tok and a.zip:
        for name, path, params in (("salling_food_waste", "food-waste/", {"zip": a.zip}), ("salling_stores", "stores/", {"zip": a.zip, "per_page": 100})):
            try:
                data = http_get_json(f"{SALLING_BASE}/{path}", {"Authorization": f"Bearer {tok}"}, params)
                (out / f"{name}_{a.zip}.json").write_text(json.dumps(data, ensure_ascii=False))
                manifest["ok"].append(name)
            except Exception as exc:  # noqa: BLE001
                manifest["failed"][name] = type(exc).__name__
    else:
        manifest["failed"]["salling"] = "no token or zip"

    key = os.environ.get("HJEMMEFRA_TJEK_API_KEY", "")
    if key and a.zip in POSTAL_CENTROIDS:
        lat, lon = POSTAL_CENTROIDS[a.zip]
        pages, offset = [], 0
        try:
            while offset < 2000:
                data = http_get_json(f"{TJEK_BASE}/offers", {"X-Api-Key": key},
                                     {"r_lat": lat, "r_lng": lon, "r_radius": a.radius, "limit": 100, "offset": offset})
                if not data:
                    break
                pages.extend(data)
                offset += 100
                if len(data) < 100:
                    break
            (out / f"tjek_offers_{a.zip}.json").write_text(json.dumps(pages, ensure_ascii=False))
            manifest["ok"].append("tjek_offers")
        except Exception as exc:  # noqa: BLE001
            manifest["failed"]["tjek_offers"] = type(exc).__name__
    else:
        manifest["failed"]["tjek"] = "no key or unknown zip centroid"

    if a.recipe_urls and Path(a.recipe_urls).exists():
        for url in [l.strip() for l in Path(a.recipe_urls).read_text().splitlines() if l.strip() and not l.startswith("#")]:
            try:
                html = http_get_text(url, {"User-Agent": "hjemmefra-recipe-import/0.1 (+structured data only)"})
                node = _find_recipe_node(_LD.findall(html))
                if node is None:
                    manifest["failed"][url] = "no Recipe JSON-LD"
                    continue
                (out / "recipes" / f"{stable_hash(url)[:16]}.json").write_text(json.dumps({"url": url, "fetched_at": now, "recipe": node}, ensure_ascii=False))
                manifest["ok"].append(url)
            except Exception as exc:  # noqa: BLE001
                manifest["failed"][url] = type(exc).__name__
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    print(json.dumps(manifest, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
