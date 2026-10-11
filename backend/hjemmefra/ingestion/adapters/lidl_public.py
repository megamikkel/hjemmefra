"""Lidl Danmark public offer pages (compliance class PUBLIC_PAGE).

Lidl renders each product tile with a `data-grid-data` JSON attribute containing title,
price, packaging text, unit price, validity (storeStartDate/storeEndDate, epoch seconds)
and, for Lidl Plus offers, a `lidlPlus` block with the member price ("Kuponpris" means the
coupon must be activated in the app). Pages are discovered from the leaflet hub page and
fetched only where robots.txt allows, rate limited. Offers are national (region 1 = DK).

What is NOT inferred: a normal price from the "-17 %" badge (rounded, unreliable), or any
package size from free text that does not parse unambiguously; such offers go to review.
"""
from __future__ import annotations

import html as htmllib
import json
import re
import time
import urllib.parse
import urllib.robotparser
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

from hjemmefra.core.ids import stable_hash
from hjemmefra.domain.offer import RawOfferRecord, SourceType
from hjemmefra.ingestion.base import ComplianceClass, FetchResult, SourceAdapter, SourceDescriptor
from hjemmefra.ingestion.packaging import parse_package

BASE = "https://www.lidl.dk"
HUBS = ["/", "/c/tilbudsavis/s10013730", "/c/lidl-plus-tilbudsavis/s10014830", "/c/lidl-plus-tilbud/s10029008"]
UA = "hjemmefra-offer-import/0.1 (+public offer pages; respects robots.txt)"
CPH = ZoneInfo("Europe/Copenhagen")
_GRID = re.compile(r'data-grid-data="([^"]+)"')
_CAMPAIGN_LINK = re.compile(r'href="(?:https://www\.lidl\.dk)?(/c/[^"#?]+/[as]\d+)"')


def _follow(path: str) -> bool:
    """Campaign pages (/a...) and offer hubs only; never general category browsing."""
    return bool(re.search(r"/a\d+$", path)) or ("tilbud" in path and re.search(r"/s\d+$", path) is not None)
FOOD_CATEGORY_HINTS = ("Mad", "Food", "Kød", "Frugt", "Grønt", "Mejeri", "Brød", "Frost", "Kolonial", "Drikke", "Fisk")


def descriptor() -> SourceDescriptor:
    return SourceDescriptor(source_id="lidl_public_pages", source_type=SourceType.PUBLIC_PAGE, compliance=ComplianceClass.PUBLIC_PAGE,
                            retailer="lidl", freshness_sla=timedelta(days=1), terms_reference="https://www.lidl.dk/robots.txt")


def _epoch_date(v) -> Optional[str]:
    try:
        return datetime.fromtimestamp(int(v), tz=timezone.utc).astimezone(CPH).date().isoformat()
    except (TypeError, ValueError):
        return None


def _iso_date(v) -> Optional[str]:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(CPH).date().isoformat()
    except ValueError:
        return None


def _packaging(text: Optional[str]) -> Optional[Tuple[Decimal, str, int, bool]]:
    """'1/2 kg' -> (0.5, kg, 1); '24 x 330 ml' -> (330, ml, 24); 'ca. 1 kg' -> approximate."""
    if not text:
        return None
    t = text.strip().lower()
    approx = t.startswith(("ca.", "ca ", "min."))
    t = re.sub(r"^(ca\.?|min\.?)\s*", "", t)
    m = re.fullmatch(r"(\d+)\s*/\s*(\d+)\s*(kg|g|l|ml|cl)", t)
    if m:
        return Decimal(m.group(1)) / Decimal(m.group(2)), m.group(3), 1, approx
    p = parse_package(t)
    if p is None:
        return None
    return p[0], p[1].value, p[2], approx


def tile_to_payload(d: dict, page_url: str) -> Optional[dict]:
    title = (d.get("fullTitle") or d.get("title") or "").strip()
    if not title:
        return None
    lp = (d.get("lidlPlus") or [None])[0]
    member = lp is not None
    price_obj = (lp or {}).get("price") or d.get("price") or {}
    rp = ((d.get("regionsPrices") or {}).get("1") or {}).get("currentPrice") or {}
    price = price_obj.get("price", rp.get("price"))
    if price is None:
        return None
    pack = _packaging((price_obj.get("packaging") or rp.get("packaging") or {}).get("text"))
    valid_from = _epoch_date(d.get("storeStartDate")) or _iso_date(rp.get("startDate"))
    valid_to = _epoch_date(d.get("storeEndDate")) or _iso_date(rp.get("endDate"))
    if not valid_from or not valid_to:
        return None  # no validity -> not usable; never guessed
    highlight = (lp or {}).get("highlightText")
    payload = {
        "external_id": f"lidl:{d.get('productId') or d.get('itemId')}:{valid_from}:{'plus' if member else 'std'}",
        "title": title, "retailer": "lidl", "scope": "NATIONAL", "valid_from": valid_from, "valid_to": valid_to,
        "offer_price": str(price), "normal_price": None, "brand": (d.get("brand") or {}).get("name") if isinstance(d.get("brand"), dict) else d.get("brand"),
        "member_only": member, "required_membership": "lidl_plus" if member else None,
        "coupon_required": bool(highlight and "kupon" in highlight.lower()),
        "assortment_text": (price_obj.get("basePrice") or {}).get("text"),
        "conditions": "; ".join(x for x in [highlight and f"Lidl Plus: {highlight}", (price_obj.get("packaging") or {}).get("text")] if x) or None,
        "category": (d.get("keyfacts") or {}).get("wonCategoryPrimary") or d.get("category"),
        "product_url": urllib.parse.urljoin(BASE, d.get("canonicalUrl") or ""), "page_url": page_url,
    }
    if pack is not None:
        q, unit, count, approx = pack
        payload.update({"package_quantity": str(q), "package_unit": unit, "package_count": count})
        if approx:
            payload["conditions"] = (payload["conditions"] or "") + "; approximate weight"
    return payload


def parse_page(html: str, page_url: str) -> List[dict]:
    out = []
    for m in _GRID.finditer(html):
        try:
            d = json.loads(htmllib.unescape(m.group(1)))
        except json.JSONDecodeError:
            continue
        p = tile_to_payload(d, page_url)
        if p:
            out.append(p)
    return out


class LidlPublicPagesAdapter(SourceAdapter):
    def __init__(self, fetch_html: Optional[Callable[[str], Tuple[int, str]]] = None, robots_txt: Optional[str] = None,
                 delay: float = 2.0, max_pages: int = 40, now: Optional[datetime] = None, food_only: bool = True):
        self.descriptor = descriptor()
        self._fetch = fetch_html or _http_fetch
        self._robots_txt = robots_txt
        self._delay, self._max_pages, self._now, self._food_only = delay, max_pages, now, food_only

    def fetch(self) -> FetchResult:
        now = self._now or datetime.now(timezone.utc)
        rp = urllib.robotparser.RobotFileParser()
        try:
            robots = self._robots_txt if self._robots_txt is not None else self._fetch(f"{BASE}/robots.txt")[1]
        except Exception as exc:  # noqa: BLE001
            return FetchResult(descriptor=self.descriptor, error=f"robots.txt unavailable: {type(exc).__name__}")
        rp.parse(robots.splitlines())
        queue: List[str] = [urllib.parse.urljoin(BASE, h) for h in HUBS]
        seen: set = set()
        records: Dict[str, RawOfferRecord] = {}
        errors = []
        fetched = 0
        while queue and fetched < self._max_pages:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            if not rp.can_fetch(UA, url):
                continue
            if fetched:
                time.sleep(self._delay)
            fetched += 1
            try:
                status, html = self._fetch(url)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{url}: {type(exc).__name__}")
                continue
            if status >= 400:
                errors.append(f"{url}: HTTP {status}")
                continue
            for href in _CAMPAIGN_LINK.findall(html):
                if not _follow(href):
                    continue
                u = urllib.parse.urljoin(BASE, href)
                if u not in seen and u not in queue:
                    queue.append(u)
            for p in parse_page(html, url):
                if self._food_only and p.get("category") and not any(h in str(p["category"]) for h in FOOD_CATEGORY_HINTS):
                    continue
                rid = f"raw_{stable_hash(self.descriptor.source_id, p['external_id'])}"
                records[rid] = RawOfferRecord(raw_id=rid, source_id=self.descriptor.source_id, source_type=SourceType.PUBLIC_PAGE,
                                              source_reference=url, captured_at=now, retailer="lidl", payload=p,
                                              snapshot_ref=f"lidl/{p['external_id']}")
        if not records and errors:
            return FetchResult(descriptor=self.descriptor, error="; ".join(errors[:3]))
        return FetchResult(descriptor=self.descriptor, records=list(records.values()), captured_at=now)


def _http_fetch(url: str) -> Tuple[int, str]:
    import httpx
    r = httpx.get(url, headers={"User-Agent": UA, "Accept-Language": "da"}, timeout=25, follow_redirects=True)
    return r.status_code, r.text
