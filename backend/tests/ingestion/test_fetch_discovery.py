"""Sitemap discovery honours robots.txt and fetching is incremental (no network)."""
import json

import httpx

from hjemmefra.tools import fetch_sources as fs

ROBOTS = "User-agent: *\nDisallow: /privat/\nCrawl-delay: 3\nSitemap: https://site.test/sitemap_index.xml\n"
INDEX = """<sitemapindex><sitemap><loc>https://site.test/post-sitemap.xml</loc></sitemap>
<sitemap><loc>https://site.test/category-sitemap.xml</loc></sitemap></sitemapindex>"""
POSTS = """<urlset>
<url><loc>https://site.test/frikadeller/</loc><lastmod>2026-09-01</lastmod></url>
<url><loc>https://site.test/lasagne/</loc><lastmod>2026-10-01</lastmod></url>
<url><loc>https://site.test/privat/hemmelig/</loc><lastmod>2026-10-02</lastmod></url>
<url><loc>https://site.test/category/aftensmad/</loc></url>
<url><loc>https://other.test/x/</loc></url>
</urlset>"""
PAGE = '<h1>{n}</h1><li itemprop="recipeIngredient">500 g hakket svinekød</li><span itemprop="totalTime" content="PT40M"></span>'


class R:
    def __init__(self, url, text, status=200):
        self.url, self.text, self.status_code = url, text, status


def fake_get(url, **kw):
    routes = {"https://site.test/robots.txt": ROBOTS, "https://site.test/sitemap_index.xml": INDEX,
              "https://site.test/post-sitemap.xml": POSTS,
              "https://site.test/frikadeller/": PAGE.format(n="Frikadeller"), "https://site.test/lasagne/": PAGE.format(n="Lasagne")}
    if url not in routes:
        return R(url, "nope", 404)
    return R(url, routes[url])


def test_discovery_respects_robots_and_skips_taxonomy(monkeypatch):
    monkeypatch.setattr(httpx, "get", fake_get)
    urls, rp, delay = fs.discover_recipe_urls("https://site.test")
    assert urls == ["https://site.test/lasagne/", "https://site.test/frikadeller/"]  # newest first, no /privat/, /category/, other host
    assert delay == 3


def test_fetch_is_incremental_and_stores_facts_only(monkeypatch, tmp_path):
    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(fs.time, "sleep", lambda s: None)
    out = tmp_path / "out"
    fs.main(["--out", str(out), "--discover-sitemap", "https://site.test", "--max-new-recipes", "1"])
    m = json.loads((out / "manifest.json").read_text())
    assert m["ok"] == ["https://site.test/lasagne/"] and m["capped_after"] == 1
    doc = json.loads(next((out / "recipes").glob("*.json")).read_text())
    assert doc["recipe"]["name"] == "Lasagne" and doc["recipe"]["totalTime"] == "PT40M"
    assert "recipeInstructions" not in doc["recipe"]
    fs.main(["--out", str(out), "--discover-sitemap", "https://site.test", "--max-new-recipes", "5"])
    m = json.loads((out / "manifest.json").read_text())
    assert m["ok"] == ["https://site.test/frikadeller/"] and m["skipped_existing"] == 1
