"""Adapter for manually administered / imported offers in a JSON document.

Used for: manual admin entry, user-supplied data, and as the demo provider.
Payload schema per record (all prices as decimal strings in DKK):
  {
    "external_id": "...", "title": "...", "retailer": "rema", "scope": "NATIONAL",
    "store_id": null, "region": null,
    "valid_from": "2026-10-05", "valid_to": "2026-10-11",
    "package_quantity": "500", "package_unit": "g", "package_count": 1,
    "normal_price": "49.95", "offer_price": "29.95",
    "multi_buy_quantity": 2, "multi_buy_price": "50.00",
    "minimum_quantity": null, "maximum_quantity": 6,
    "member_only": false, "required_membership": null, "coupon_required": false,
    "deposit": "0", "assortment_text": "...", "conditions": "...",
    "canonical_product_id": "CHICKEN_BREAST"   # optional pre-resolved mapping
    "ocr": {"offer_price": {"raw_value": "2995", "confidence": 0.61, "source_location": "p3"}}
  }
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from hjemmefra.core.ids import stable_hash
from hjemmefra.domain.offer import OcrField, RawOfferRecord
from hjemmefra.ingestion.base import FetchResult, SourceAdapter, SourceDescriptor


class ManualJsonAdapter(SourceAdapter):
    def __init__(self, descriptor: SourceDescriptor, records: Optional[Iterable[dict]] = None,
                 path: Optional[Path] = None, captured_at: Optional[datetime] = None):
        self.descriptor = descriptor
        self._records = list(records) if records is not None else None
        self._path = path
        self._captured_at = captured_at or datetime.now(timezone.utc)

    def fetch(self) -> FetchResult:
        try:
            if self._records is None:
                if self._path is None:
                    raise FileNotFoundError("no records and no path configured")
                self._records = json.loads(Path(self._path).read_text(encoding="utf-8"))
        except Exception as exc:  # graceful degradation
            return FetchResult(descriptor=self.descriptor, error=f"{type(exc).__name__}: {exc}")

        out = []
        for rec in self._records:
            ext = str(rec.get("external_id") or stable_hash(self.descriptor.source_id, json.dumps(rec, sort_keys=True, default=str)))
            ocr = {k: OcrField(**v) for k, v in (rec.get("ocr") or {}).items()}
            out.append(
                RawOfferRecord(
                    raw_id=f"raw_{stable_hash(self.descriptor.source_id, ext)}",
                    source_id=self.descriptor.source_id,
                    source_type=self.descriptor.source_type,
                    source_reference=str(self._path) if self._path else f"{self.descriptor.source_id}:{ext}",
                    captured_at=self._captured_at,
                    retailer=rec.get("retailer") or self.descriptor.retailer,
                    payload=rec,
                    ocr_fields=ocr,
                    snapshot_ref=f"{self.descriptor.source_id}/{ext}",
                )
            )
        return FetchResult(descriptor=self.descriptor, records=out, captured_at=self._captured_at)
