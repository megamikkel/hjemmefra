"""REMA 1000 public pages (compliance class PUBLIC_PAGE).

REMA's recipe pages (/opskrifter/...) and front page embed the products they use, with
REMA's own price list per product: regular price and campaign ("Avisvare") prices, each
with starting_at/ending_at, max_quantity, price_over_max_quantity and deposit. The
leaflet itself is loaded from /api, which robots.txt disallows, so it is NOT used; this
adapter only reads robots-allowed HTML pages. Coverage is therefore partial: products
that appear on recipe pages.

Validity is conservative: an `ending_at` of exactly midnight UTC is treated as exclusive,
so the offer ends the day before. Products not available in all stores are skipped
(their store scope is unknown).
"""
from __future__ import annotations

import re
import time
import urllib.parse
import urllib.robotparser
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from hjemmefra.core.ids import stable_hash
from hjemmefra.domain.offer import RawOfferRecord, SourceType
from hjemmefra.ingestion.base import ComplianceClass, FetchResult, SourceAdapter, SourceDescriptor
from hjemmefra.ingestion.nuxt import Devalue, extract_payload
from hjemmefra.ingestion.packaging import parse_package

BASE = "https://rema1000.dk"
UA = "hjemmefra-offer-import/0.1 (+public pages; respects robots.txt)"
CPH = ZoneInfo("Europe/Copenhagen")
_LINK = re.compile(r'"(/opskrifter(?:/[a-z0-9\-]+)+)"')


def descriptor() -> SourceDescriptor:
    return SourceDescriptor(source_id="rema_public_pages", source_type=SourceType.PUBLIC_PAGE, compliance=ComplianceClass.PUBLIC_PAGE,
                            retailer="rema", freshness_sla=timedelta(days=1), terms_reference="https://rema1000.dk/robots.txt")


REGULAR_PRICE_HORIZON_DAYS = 13  # regular shelf prices are re-confirmed on every run


def _dt(v: Optional[str]) -> Optional[datetime]:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def _date(v: Optional[str], end: bool = False) -> Optional[str]:
    dt = _dt(v)
    if dt is None:
        return None
    local = dt.astimezone(CPH)
    if end:
        local = local - timedelta(seconds=1)  # end instants are exclusive
        if local.hour < 6:  # an end in the small hours means the last full shopping day is the day before
            local = local - timedelta(days=1)
    return local.date().isoformat()


def product_records(p: dict, page_url: str, today: str) -> List[dict]:
    """One payload per currently relevant price entry (campaign or regular)."""
    if not p.get("is_available_in_all_stores", True):
        return []
    prices = [x for x in (p.get("prices") or []) if isinstance(x, dict) and x.get("price") is not None]
    if not prices:
        return []
    name = str(p.get("name") or "").strip()
    underline = str(p.get("underline") or "")
    title = f"{name.capitalize()} {underline.split('/')[0].strip().lower()}".strip()
    pack = parse_package(underline.split("/")[0]) if underline else None
    regular = [x for x in prices if not x.get("is_campaign")]
    out = []
    for e in prices:
        vf, vt = _date(e.get("starting_at")), _date(e.get("ending_at"), end=True)
        if not vf or not vt or vt < today:
            continue
        normal = None
        if e.get("is_campaign"):
            # normal price = the regular entry that starts nearest the campaign end (within 3 days), i.e. what it reverts to
            end = _dt(e.get("ending_at"))
            cands = [(abs((_dt(r.get("starting_at")) - end).total_seconds()), r) for r in regular if _dt(r.get("starting_at")) and end]
            cands = [c for c in cands if c[0] <= 3 * 86400]
            if cands:
                normal = min(cands, key=lambda c: c[0])[1].get("price")
        else:
            horizon = (datetime.fromisoformat(today) + timedelta(days=REGULAR_PRICE_HORIZON_DAYS)).date().isoformat()
            vt = min(vt, horizon)
            vf = max(vf, today) if vf < today else vf
        payload = {
            "external_id": f"rema:{p.get('id')}:{e.get('starting_at')}:{'c' if e.get('is_campaign') else 'r'}",
            "title": title, "retailer": "rema", "scope": "NATIONAL", "valid_from": vf, "valid_to": vt,
            "offer_price": str(e["price"]), "normal_price": str(normal if e.get("is_campaign") else e["price"]) if (normal or not e.get("is_campaign")) else None,
            "maximum_quantity": e.get("max_quantity"), "deposit": str(e.get("deposit") or 0),
            "assortment_text": underline, "conditions": "; ".join(x for x in [
                "Avisvare" if e.get("is_advertised") else None,
                f"over {e['max_quantity']} stk: {e['price_over_max_quantity']} kr" if e.get("max_quantity") and e.get("price_over_max_quantity") else None,
            ] if x) or None,
            "is_campaign": bool(e.get("is_campaign")), "rema_product_id": p.get("id"), "page_url": page_url,
        }
        if e.get("max_quantity") and e.get("price_over_max_quantity") is not None:
            payload["normal_price"] = payload["normal_price"] or str(e["price_over_max_quantity"])
        if pack:
            payload.update({"package_quantity": str(pack[0]), "package_unit": pack[1].value, "package_count": pack[2]})
        out.append(payload)
    return out


def parse_page(html: str, page_url: str, today: str) -> Tuple[List[dict], List[str]]:
    data = extract_payload(html)
    links = sorted(set(_LINK.findall(html)))
    if data is None:
        return [], links
    dv = Devalue(data)
    out, seen = [], set()
    for p in dv.objects_with("prices", "name", "id"):
        if not isinstance(p, dict) or p.get("id") in seen:
            continue
        seen.add(p.get("id"))
        out.extend(product_records(p, page_url, today))
    return out, links


class RemaPublicPagesAdapter(SourceAdapter):
    def __init__(self, fetch_html: Optional[Callable[[str], Tuple[int, str]]] = None, robots_txt: Optional[str] = None,
                 delay: float = 2.0, max_pages: int = 60, now: Optional[datetime] = None):
        self.descriptor = descriptor()
        self._fetch = fetch_html or _http_fetch
        self._robots_txt, self._delay, self._max_pages, self._now = robots_txt, delay, max_pages, now

    def fetch(self) -> FetchResult:
        now = self._now or datetime.now(timezone.utc)
        today = now.astimezone(CPH).date().isoformat()
        rp = urllib.robotparser.RobotFileParser()
        try:
            robots = self._robots_txt if self._robots_txt is not None else self._fetch(f"{BASE}/robots.txt")[1]
        except Exception as exc:  # noqa: BLE001
            return FetchResult(descriptor=self.descriptor, error=f"robots.txt unavailable: {type(exc).__name__}")
        rp.parse(robots.splitlines())
        queue, seen, fetched, errors = [f"{BASE}/", f"{BASE}/opskrifter"], set(), 0, []
        records: Dict[str, RawOfferRecord] = {}
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
            payloads, links = parse_page(html, url, today)
            for l in links:
                u = urllib.parse.urljoin(BASE, l)
                if u not in seen and u not in queue:
                    queue.append(u)
            for pl in payloads:
                rid = f"raw_{stable_hash(self.descriptor.source_id, pl['external_id'])}"
                records[rid] = RawOfferRecord(raw_id=rid, source_id=self.descriptor.source_id, source_type=SourceType.PUBLIC_PAGE,
                                              source_reference=url, captured_at=now, retailer="rema", payload=pl,
                                              snapshot_ref=f"rema/{pl['external_id']}")
        if not records and errors:
            return FetchResult(descriptor=self.descriptor, error="; ".join(errors[:3]))
        return FetchResult(descriptor=self.descriptor, records=list(records.values()), captured_at=now)


def _http_fetch(url: str) -> Tuple[int, str]:
    import httpx
    r = httpx.get(url, headers={"User-Agent": UA, "Accept-Language": "da"}, timeout=25, follow_redirects=True)
    return r.status_code, r.text
