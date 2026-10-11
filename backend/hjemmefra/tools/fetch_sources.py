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
import time
import urllib.parse
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path

from hjemmefra.core.ids import stable_hash
from hjemmefra.ingestion.adapters.salling import BASE as SALLING_BASE
from hjemmefra.ingestion.adapters.tjek import BASE as TJEK_BASE
from hjemmefra.ingestion.http import http_get_json, http_get_text
from hjemmefra.location.geo import POSTAL_CENTROIDS
import httpx

from hjemmefra.recipes.importer import _LD, extract_recipe_node


UA = "hjemmefra-recipe-import/0.2 (+facts only; respects robots.txt)"
FACT_KEYS = {"@type", "name", "recipeIngredient", "recipeYield", "prepTime", "cookTime", "totalTime", "recipeCuisine",
             "recipeCategory", "keywords", "_extracted_from"}
_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>(?:\s*<lastmod>\s*([^<\s]+)\s*</lastmod>)?", re.I)
_SKIP_PATH = re.compile(r"/(category|kategori|tag|tags|page|author|forfatter|wp-content|feed|om-|kontakt|cookie|privat|search|soeg)", re.I)


def _host(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower()


def discover_recipe_urls(root: str, max_sitemaps: int = 20):
    """Return (urls newest-first, robotparser, crawl_delay) from robots.txt-declared or conventional sitemaps."""
    base = root.rstrip("/")
    rp = urllib.robotparser.RobotFileParser()
    robots_txt = httpx.get(f"{base}/robots.txt", headers={"User-Agent": UA}, timeout=20, follow_redirects=True)
    rp.parse(robots_txt.text.splitlines() if robots_txt.status_code < 400 else [])
    crawl_delay = rp.crawl_delay(UA)
    sitemaps = list(rp.site_maps() or []) or [f"{base}/sitemap_index.xml", f"{base}/sitemap.xml"]
    pages: dict[str, str] = {}
    queue, visited = list(sitemaps), 0
    while queue and visited < max_sitemaps:
        sm = queue.pop(0)
        visited += 1
        r = httpx.get(sm, headers={"User-Agent": UA}, timeout=30, follow_redirects=True)
        if r.status_code >= 400:
            continue
        for loc, lastmod in _LOC.findall(r.text):
            if loc.endswith(".xml") or "sitemap" in loc.split("/")[-1]:
                # nested sitemap: prefer post/recipe sitemaps, skip taxonomy/page/image sitemaps
                name = loc.split("/")[-1].lower()
                if any(x in name for x in ("post", "recipe", "opskrift")) and not any(x in name for x in ("category", "tag", "author", "page-sitemap")):
                    queue.append(loc)
            elif _host(loc) == _host(base) and not _SKIP_PATH.search(urllib.parse.urlparse(loc).path) and urllib.parse.urlparse(loc).path.strip("/"):
                pages[loc] = lastmod or ""
    ordered = sorted(pages, key=lambda u: (pages[u], u), reverse=True)
    return [u for u in ordered if rp.can_fetch(UA, u)], rp, crawl_delay


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--zip", default=os.environ.get("HJEMMEFRA_SOURCE_POSTAL_CODE", ""))
    ap.add_argument("--radius", type=int, default=10000)
    ap.add_argument("--recipe-urls", help="text file with one URL per line")
    ap.add_argument("--discover-sitemap", action="append", default=[], help="site root whose sitemap lists recipe pages (robots.txt is honoured)")
    ap.add_argument("--max-new-recipes", type=int, default=150, help="cap on newly fetched recipe pages per run")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between page requests (raised to the site's Crawl-delay)")
    ap.add_argument("--public-offers", default="", help="comma list of public-page offer sources: lidl,rema")
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

    for src in [x.strip() for x in a.public_offers.split(",") if x.strip()]:
        try:
            if src == "lidl":
                from hjemmefra.ingestion.adapters.lidl_public import LidlPublicPagesAdapter as A
            elif src == "rema":
                from hjemmefra.ingestion.adapters.rema_public import RemaPublicPagesAdapter as A
            else:
                manifest["failed"][f"offers:{src}"] = "unknown source"
                continue
            res = A(delay=a.delay).fetch()
            if not res.ok:
                manifest["failed"][f"offers:{src}"] = res.error
                continue
            (out / f"offers_{src}.json").write_text(json.dumps([json.loads(r.model_dump_json()) for r in res.records], ensure_ascii=False))
            manifest["ok"].append(f"offers:{src}:{len(res.records)}")
        except Exception as exc:  # noqa: BLE001
            manifest["failed"][f"offers:{src}"] = f"{type(exc).__name__}: {exc}"[:200]

    urls: list[str] = []
    if a.recipe_urls and Path(a.recipe_urls).exists():
        urls += [l.strip() for l in Path(a.recipe_urls).read_text().splitlines() if l.strip() and not l.startswith("#")]
    delays: dict[str, float] = {}
    robots: dict[str, object] = {}
    for root in a.discover_sitemap:
        try:
            found, rp, crawl_delay = discover_recipe_urls(root)
            robots[_host(root)] = rp
            delays[_host(root)] = max(a.delay, crawl_delay or 0)
            manifest.setdefault("discovery", {})[root] = {"urls": len(found), "crawl_delay": crawl_delay}
            urls += found
        except Exception as exc:  # noqa: BLE001
            manifest["failed"][f"discover:{root}"] = f"{type(exc).__name__}: {exc}"[:200]
    seen, new_fetches = set(), 0
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        target = out / "recipes" / f"{stable_hash(url)[:16]}.json"
        if target.exists():
            manifest.setdefault("skipped_existing", 0)
            manifest["skipped_existing"] += 1
            continue
        rp = robots.get(_host(url))
        if rp is not None and not rp.can_fetch(UA, url):
            manifest["failed"][url] = "disallowed by robots.txt"
            continue
        if new_fetches >= a.max_new_recipes:
            manifest["capped_after"] = a.max_new_recipes
            break
        new_fetches += 1
        if new_fetches > 1:
            time.sleep(delays.get(_host(url), a.delay))
        if True:
            try:
                r = httpx.get(url, headers={"User-Agent": UA, "Accept-Language": "da"},
                              timeout=20, follow_redirects=True)
                html = r.text
                title = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
                diag = {"status": r.status_code, "final_url": str(r.url), "bytes": len(html),
                        "title": (title.group(1).strip()[:80] if title else None), "ld_json_blocks": len(_LD.findall(html)),
                        "ld_types": sorted(set(re.findall(r'"@type"\s*:\s*"([A-Za-z]+)"', html)))[:15],
                        "microdata_ingredients": html.count("recipeIngredient")}
                if urllib.parse.urlparse(str(r.url)).path.strip("/") == "":
                    manifest["failed"][url] = "redirected to site front page (page no longer exists)"
                    continue
                if r.status_code >= 400:
                    manifest.setdefault("diagnostics", {})[url] = diag
                    manifest["failed"][url] = f"HTTP {r.status_code}"
                    continue
                node = extract_recipe_node(html)
                if node is None:
                    manifest.setdefault("diagnostics", {})[url] = diag
                    manifest["failed"][url] = "no Recipe structured data"
                    continue
                # Store facts only (name, ingredients, times, yield). Method text is not copied; users follow the source link.
                facts = {k: v for k, v in node.items() if k in FACT_KEYS}
                target.write_text(json.dumps({"url": str(r.url), "requested_url": url, "fetched_at": now, "recipe": facts}, ensure_ascii=False))
                manifest["ok"].append(url)
            except Exception as exc:  # noqa: BLE001
                manifest["failed"][url] = type(exc).__name__
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    print(json.dumps(manifest, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
