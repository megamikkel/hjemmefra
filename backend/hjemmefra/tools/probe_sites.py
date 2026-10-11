"""Reconnaissance for retailer offer pages (PUBLIC_PAGE sources).

For each site: read robots.txt, fetch the front page, collect same-host links that look like
offer/leaflet pages, and fetch a few (robots-allowed, rate limited). Records status, size,
JSON-LD @types, embedded-JSON markers and price-like counts, and keeps a truncated copy of
each page so parsers can be written against real markup. Nothing is fetched that robots.txt
disallows for our user agent.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.robotparser
from pathlib import Path

import httpx

UA = "hjemmefra-offer-probe/0.1 (+public offer pages; respects robots.txt)"
LINK = re.compile(r'href\s*=\s*["\']([^"\'#]+)["\']', re.I)
OFFER_WORDS = re.compile(r"(tilbud|avis|offer|ugens|kampagne|deals|rabat)", re.I)
MARKERS = ["__NEXT_DATA__", "__NUXT__", "window.__INITIAL_STATE__", "window.__PRELOADED_STATE__", "application/ld+json",
           "data-price", "itemprop=\"price\"", "\"price\"", "kr.", "ipaper", "publitas", "flipp", "issuu", "pdf"]


def probe(root: str, out: Path, max_pages: int, delay: float) -> dict:
    host = urllib.parse.urlparse(root).netloc
    res: dict = {"root": root}
    rp = urllib.robotparser.RobotFileParser()
    try:
        r = httpx.get(urllib.parse.urljoin(root, "/robots.txt"), headers={"User-Agent": UA}, timeout=20, follow_redirects=True)
        res["robots_status"] = r.status_code
        lines = r.text.splitlines() if r.status_code < 400 else []
        rp.parse(lines)
        (out / f"{host}.robots.txt").write_text(r.text[:20000])
        res["crawl_delay"] = rp.crawl_delay(UA)
        res["sitemaps"] = rp.site_maps()
    except Exception as exc:  # noqa: BLE001
        res["robots_error"] = type(exc).__name__
        return res
    delay = max(delay, res.get("crawl_delay") or 0)
    pages = [root]
    res["pages"] = []
    seen = set()
    while pages and len(res["pages"]) < max_pages:
        url = pages.pop(0)
        if url in seen:
            continue
        seen.add(url)
        if not rp.can_fetch(UA, url):
            res["pages"].append({"url": url, "skipped": "disallowed by robots.txt"})
            continue
        if res["pages"]:
            time.sleep(delay)
        try:
            r = httpx.get(url, headers={"User-Agent": UA, "Accept-Language": "da"}, timeout=25, follow_redirects=True)
        except Exception as exc:  # noqa: BLE001
            res["pages"].append({"url": url, "error": type(exc).__name__})
            continue
        html = r.text
        info = {"url": url, "final_url": str(r.url), "status": r.status_code, "bytes": len(html),
                "content_type": r.headers.get("content-type", ""),
                "title": (re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I) or [None, None])[1],
                "ld_types": sorted(set(re.findall(r'"@type"\s*:\s*"([A-Za-z]+)"', html)))[:20],
                "markers": {m: html.count(m) for m in MARKERS if m in html}}
        fname = re.sub(r"[^a-z0-9]+", "_", url.lower())[-90:] + ".html"
        (out / fname).write_text(html[:400_000])
        info["saved_as"] = fname
        res["pages"].append(info)
        if url == root:
            links = []
            for href in LINK.findall(html):
                u = urllib.parse.urljoin(str(r.url), href)
                p = urllib.parse.urlparse(u)
                if p.netloc.endswith(host.replace("www.", "")) and OFFER_WORDS.search(p.path) and u not in links:
                    links.append(u.split("?")[0])
            res["offer_links"] = links[:40]
            pages.extend(links[: max_pages])
    return res


def save_sitemaps(url: str, out: Path, delay: float, max_children: int = 8) -> dict:
    res = {"sitemap": url, "children": []}
    try:
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=30, follow_redirects=True)
    except Exception as exc:  # noqa: BLE001
        res["error"] = type(exc).__name__
        return res
    name = re.sub(r"[^a-z0-9]+", "_", url.lower())[-80:]
    (out / f"sm_{name}.xml").write_text(r.text[:2_000_000])
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text)
    res.update(status=r.status_code, locs=len(locs), sample=locs[:30])
    for child in [l for l in locs if l.endswith(".xml")][:max_children]:
        time.sleep(delay)
        try:
            c = httpx.get(child, headers={"User-Agent": UA}, timeout=30, follow_redirects=True)
        except Exception as exc:  # noqa: BLE001
            res["children"].append({"url": child, "error": type(exc).__name__})
            continue
        cl = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", c.text)
        cname = re.sub(r"[^a-z0-9]+", "_", child.lower())[-80:]
        (out / f"sm_{cname}.xml").write_text(c.text[:2_000_000])
        res["children"].append({"url": child, "status": c.status_code, "locs": len(cl), "sample": cl[:15]})
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--site", action="append", required=True)
    ap.add_argument("--max-pages", type=int, default=6)
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--sitemap", action="append", default=[], help="save this sitemap and the first child sitemaps")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    report = [probe(s, out, a.max_pages, a.delay) for s in a.site]
    for sm in a.sitemap:
        report.append(save_sitemaps(sm, out, a.delay))
    (out / "probe_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
    print(json.dumps(report, indent=1, ensure_ascii=False, default=str)[:20000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
