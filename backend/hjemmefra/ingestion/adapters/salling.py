"""Salling Group official API (Netto, Bilka, føtex) - compliance class OFFICIAL_API.

Docs: https://developer.sallinggroup.com. Requires a bearer token (HJEMMEFRA_SALLING_API_TOKEN).
Two endpoints are used:
  GET /v1/food-waste/?zip=XXXX   -> store-specific clearance offers ("datovarer") with real stock counts
  GET /v1/stores/?zip=XXXX        -> physical stores with coordinates (for the store catalog)
Clearance offers are store-specific, short-lived and have a stock count; they are
mapped to scope=STORE. Regular weekly leaflet offers are NOT in this API (see tjek.py).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from hjemmefra.core.ids import stable_hash
from hjemmefra.domain.offer import RawOfferRecord, SourceType
from hjemmefra.domain.store import Store
from hjemmefra.ingestion.base import ComplianceClass, FetchResult, SourceAdapter, SourceDescriptor, SourceUnavailable
from hjemmefra.ingestion.http import http_get_json
from hjemmefra.ingestion.packaging import parse_package

BASE = "https://api.sallinggroup.com/v1"
BRAND_TO_CHAIN = {"netto": "netto", "bilka": "bilka", "foetex": "foetex", "føtex": "foetex", "salling": "salling", "basalt": "basalt"}


def descriptor(brand: str = "salling") -> SourceDescriptor:
    from datetime import timedelta
    return SourceDescriptor(source_id=f"salling_foodwaste_{brand}", source_type=SourceType.OFFICIAL_API,
                            compliance=ComplianceClass.OFFICIAL_API, retailer=brand, freshness_sla=timedelta(hours=6),
                            terms_reference="https://developer.sallinggroup.com/terms")


class SallingFoodWasteAdapter(SourceAdapter):
    def __init__(self, token: str, zip_code: str, fetch: Callable[..., Any] = http_get_json, now: Optional[datetime] = None):
        self.descriptor = descriptor()
        self._token = token
        self._zip = zip_code
        self._fetch = fetch
        self._now = now

    def fetch(self) -> FetchResult:
        if not self._token:
            return FetchResult(descriptor=self.descriptor, error="missing API token (HJEMMEFRA_SALLING_API_TOKEN)")
        try:
            data = self._fetch(f"{BASE}/food-waste/", {"Authorization": f"Bearer {self._token}"}, {"zip": self._zip})
        except SourceUnavailable as exc:
            return FetchResult(descriptor=self.descriptor, error=str(exc))
        except Exception as exc:  # noqa: BLE001
            return FetchResult(descriptor=self.descriptor, error=f"{type(exc).__name__}")
        now = self._now or datetime.now(timezone.utc)
        records: List[RawOfferRecord] = []
        for entry in data or []:
            store = entry.get("store") or {}
            brand = str(store.get("brand", "")).lower()
            chain = BRAND_TO_CHAIN.get(brand, brand)
            store_id = f"salling_{store.get('id')}"
            for cl in entry.get("clearances") or []:
                offer, product = cl.get("offer") or {}, cl.get("product") or {}
                title = product.get("description") or ""
                pkg = parse_package(title)
                payload = {
                    "external_id": f"{store_id}:{offer.get('ean') or product.get('ean')}:{offer.get('startTime')}",
                    "title": title, "retailer": chain, "scope": "STORE", "store_id": store_id,
                    "valid_from": str(offer.get("startTime", ""))[:10], "valid_to": str(offer.get("endTime", ""))[:10],
                    "normal_price": _dec(offer.get("originalPrice")), "offer_price": _dec(offer.get("newPrice")),
                    "currency": offer.get("currency", "DKK"), "ean": offer.get("ean"),
                    "stock": offer.get("stock"), "stock_unit": offer.get("stockUnit"),
                    "conditions": "Datovare/udsalg - begrænset antal",
                }
                if pkg:
                    payload.update({"package_quantity": str(pkg[0]), "package_unit": pkg[1].value, "package_count": pkg[2]})
                records.append(RawOfferRecord(raw_id=f"raw_{stable_hash(self.descriptor.source_id, payload['external_id'])}",
                                              source_id=self.descriptor.source_id, source_type=SourceType.OFFICIAL_API,
                                              source_reference=f"{BASE}/food-waste/?zip={self._zip}", captured_at=now,
                                              retailer=chain, payload=payload, snapshot_ref=f"salling/{payload['external_id']}"))
        return FetchResult(descriptor=self.descriptor, records=records, captured_at=now)


def _dec(v) -> Optional[str]:
    return None if v is None else str(v)


def fetch_salling_stores(token: str, zip_code: str, fetch: Callable[..., Any] = http_get_json) -> List[Store]:
    data = fetch(f"{BASE}/stores/", {"Authorization": f"Bearer {token}"}, {"zip": zip_code, "per_page": 100})
    out: List[Store] = []
    for s in data or []:
        addr = s.get("address") or {}
        coords = s.get("coordinates") or [None, None]  # [lon, lat]
        brand = str(s.get("brand", "")).lower()
        out.append(Store(store_id=f"salling_{s.get('id')}", chain_id=BRAND_TO_CHAIN.get(brand, brand), name=s.get("name", ""),
                         address=addr.get("street"), postal_code=str(addr.get("zip", zip_code)), region=f"zip:{addr.get('zip', zip_code)}",
                         lat=coords[1], lon=coords[0], opening_hours={"hours": s.get("hours")} if s.get("hours") else None))
    return out
