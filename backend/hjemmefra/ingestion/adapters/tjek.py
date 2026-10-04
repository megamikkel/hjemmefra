"""Tjek (formerly eTilbudsavis / ShopGun) offers API - weekly leaflet offers for most Danish chains.

Compliance class OFFICIAL_API: requires a developer API key under Tjek's terms
(HJEMMEFRA_TJEK_API_KEY). Endpoint: GET https://squid-api.tjek.com/v2/offers with
r_lat / r_lng / r_radius / dealer_ids. Offers returned for a location are the ones
valid for that area; they are mapped to scope=REGIONAL with region "tjek:<postal>"
and stores imported for the same postal area share that region. Leaflet images/PDFs
are not scraped; only the structured offer objects are used.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from hjemmefra.core.ids import stable_hash
from hjemmefra.domain.offer import RawOfferRecord, SourceType
from hjemmefra.ingestion.base import ComplianceClass, FetchResult, SourceAdapter, SourceDescriptor, SourceUnavailable
from hjemmefra.ingestion.http import http_get_json

BASE = "https://squid-api.tjek.com/v2"
DEALER_TO_CHAIN = {"lidl": "lidl", "rema 1000": "rema", "netto": "netto", "bilka": "bilka", "føtex": "foetex", "fotex": "foetex",
                   "meny": "meny", "spar": "spar", "superbrugsen": "superbrugsen", "kvickly": "kvickly", "aldi": "aldi", "365discount": "365discount"}
UNIT_SYMBOL = {"g": "g", "kg": "kg", "ml": "ml", "cl": "cl", "dl": "dl", "l": "l", "pcs": "stk", "stk": "stk"}


def descriptor() -> SourceDescriptor:
    return SourceDescriptor(source_id="tjek_offers", source_type=SourceType.OFFICIAL_API, compliance=ComplianceClass.OFFICIAL_API,
                            retailer="multi", freshness_sla=timedelta(days=1), terms_reference="https://tjek.com/developers")


class TjekOffersAdapter(SourceAdapter):
    def __init__(self, api_key: str, lat: float, lon: float, radius_m: int, postal_code: str,
                 dealer_ids: Optional[List[str]] = None, fetch: Callable[..., Any] = http_get_json, now: Optional[datetime] = None,
                 page_size: int = 100, max_pages: int = 20):
        self.descriptor = descriptor()
        self._key, self._lat, self._lon, self._radius, self._postal = api_key, lat, lon, radius_m, postal_code
        self._dealers, self._fetch, self._now, self._page, self._max_pages = dealer_ids, fetch, now, page_size, max_pages

    def fetch(self) -> FetchResult:
        if not self._key:
            return FetchResult(descriptor=self.descriptor, error="missing API key (HJEMMEFRA_TJEK_API_KEY)")
        now = self._now or datetime.now(timezone.utc)
        records: List[RawOfferRecord] = []
        try:
            for page in range(self._max_pages):
                params: Dict[str, Any] = {"r_lat": self._lat, "r_lng": self._lon, "r_radius": self._radius,
                                          "limit": self._page, "offset": page * self._page, "order_by": "-publication_date"}
                if self._dealers:
                    params["dealer_ids"] = ",".join(self._dealers)
                data = self._fetch(f"{BASE}/offers", {"X-Api-Key": self._key}, params)
                if not data:
                    break
                for o in data:
                    rec = self._map(o, now)
                    if rec:
                        records.append(rec)
                if len(data) < self._page:
                    break
        except SourceUnavailable as exc:
            if not records:
                return FetchResult(descriptor=self.descriptor, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            return FetchResult(descriptor=self.descriptor, error=f"{type(exc).__name__}")
        return FetchResult(descriptor=self.descriptor, records=records, captured_at=now)

    def _map(self, o: dict, now: datetime) -> Optional[RawOfferRecord]:
        dealer = (o.get("dealer") or {}).get("name") or o.get("branding", {}).get("name") or ""
        chain = DEALER_TO_CHAIN.get(dealer.strip().lower())
        if chain is None:
            return None  # unknown dealer: not in our chain catalog
        pricing = o.get("pricing") or {}
        q = o.get("quantity") or {}
        size, pieces, unit = q.get("size") or {}, q.get("pieces") or {}, (q.get("unit") or {}).get("symbol")
        payload: Dict[str, Any] = {
            "external_id": str(o.get("id")), "title": o.get("heading") or "", "retailer": chain, "scope": "REGIONAL",
            "region": f"tjek:{self._postal}", "valid_from": str(o.get("run_from", ""))[:10], "valid_to": str(o.get("run_till", ""))[:10],
            "offer_price": _s(pricing.get("price")), "normal_price": _s(pricing.get("pre_price")), "currency": pricing.get("currency", "DKK"),
            "assortment_text": o.get("description"), "catalog_id": o.get("catalog_id"),
        }
        if unit in UNIT_SYMBOL and size.get("from") is not None and size.get("from") == size.get("to"):
            payload.update({"package_quantity": _s(size["from"]), "package_unit": UNIT_SYMBOL[unit],
                            "package_count": int(pieces.get("from") or 1) if pieces.get("from") == pieces.get("to") else 1})
        elif unit in UNIT_SYMBOL and size.get("from") is not None:
            payload["conditions"] = f"variable size {size.get('from')}-{size.get('to')} {unit}"  # UNKNOWN_PACKAGE_SIZE -> review
        return RawOfferRecord(raw_id=f"raw_{stable_hash(self.descriptor.source_id, payload['external_id'])}", source_id=self.descriptor.source_id,
                              source_type=SourceType.OFFICIAL_API, source_reference=f"{BASE}/offers/{o.get('id')}", captured_at=now,
                              retailer=chain, payload=payload, snapshot_ref=f"tjek/{o.get('id')}")


def _s(v) -> Optional[str]:
    return None if v is None else str(v)
