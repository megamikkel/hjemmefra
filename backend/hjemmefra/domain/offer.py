from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from hjemmefra.core.confidence import Confidence, MatchConfidence
from hjemmefra.core.units import Unit
from hjemmefra.domain.store import OfferScope


class SourceType(str, Enum):
    OFFICIAL_API = "OFFICIAL_API"
    LICENSED_FEED = "LICENSED_FEED"
    PUBLIC_PAGE = "PUBLIC_PAGE"
    PDF_LEAFLET = "PDF_LEAFLET"
    IMAGE_OCR = "IMAGE_OCR"
    USER_SUPPLIED = "USER_SUPPLIED"
    MANUAL = "MANUAL"
    DEMO = "DEMO"
    OTHER = "OTHER"


class ValidationStatus(str, Enum):
    NORMAL = "NORMAL"
    SUSPICIOUS = "SUSPICIOUS"
    INVALID = "INVALID"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


class OcrField(BaseModel):
    raw_value: str
    normalized_value: Optional[str] = None
    confidence: float  # 0..1
    source_location: Optional[str] = None  # e.g. "page 3, box (120,340,200,380)"


class RawOfferRecord(BaseModel):
    """Raw record exactly as captured from a source. Never mutated."""
    raw_id: str
    source_id: str
    source_type: SourceType
    source_reference: str  # url / file / feed id
    captured_at: datetime
    retailer: str
    payload: dict  # unparsed / semi-parsed representation
    ocr_fields: dict[str, OcrField] = Field(default_factory=dict)
    snapshot_ref: Optional[str] = None  # pointer to stored raw blob


class NormalizedOffer(BaseModel):
    offer_id: str
    raw_id: str
    source_id: str
    source_type: SourceType
    source_reference: str
    captured_at: datetime
    last_verified_at: datetime

    retailer: str  # chain_id
    scope: OfferScope
    store_id: Optional[str] = None  # when scope == STORE
    region: Optional[str] = None

    valid_from: date
    valid_to: date

    raw_title: str
    canonical_product_id: Optional[str] = None
    match_confidence: MatchConfidence = MatchConfidence.UNMATCHED
    brand: Optional[str] = None
    variant: Optional[str] = None

    package_quantity: Optional[Decimal] = None  # e.g. 500
    package_unit: Optional[Unit] = None  # e.g. g
    package_count: int = 1  # e.g. 2 x 500 g -> 2
    # total quantity in package = package_quantity * package_count

    currency: str = "DKK"
    normal_price_minor: Optional[int] = None  # stated normal price
    offer_price_minor: Optional[int] = None  # single unit price under offer
    multi_buy_quantity: Optional[int] = None  # e.g. 2 for "2 for 50"
    multi_buy_price_minor: Optional[int] = None  # e.g. 5000
    minimum_quantity: Optional[int] = None
    maximum_quantity: Optional[int] = None
    member_only: bool = False
    required_membership: Optional[str] = None
    coupon_required: bool = False
    deposit_minor: int = 0  # pant per package
    assortment_text: Optional[str] = None
    conditions: Optional[str] = None

    price_confidence: Confidence = Confidence.UNKNOWN
    validation_status: ValidationStatus = ValidationStatus.REQUIRES_REVIEW
    validation_notes: List[str] = Field(default_factory=list)
    fingerprint: str = ""  # idempotency key
    version: int = 1

    # ---- derived -----------------------------------------------------
    @property
    def total_quantity(self) -> Optional[Decimal]:
        if self.package_quantity is None:
            return None
        return self.package_quantity * self.package_count

    def is_valid_on(self, day: date) -> bool:
        return self.valid_from <= day <= self.valid_to

    def applies_to_store(self, store_id: str, chain_id: str, region: Optional[str]) -> bool:
        if self.retailer != chain_id:
            return False
        if self.scope == OfferScope.STORE:
            return self.store_id == store_id
        if self.scope in (OfferScope.REGIONAL, OfferScope.LOCAL):
            return self.region is not None and self.region == region
        return True


class PriceObservation(BaseModel):
    """Historical price point used for reference prices and sanity checks."""
    canonical_product_id: str
    retailer: str
    observed_on: date
    unit_price_minor_per_base: Decimal  # øre per base unit (g/ml/stk)
    is_offer: bool
    source_id: str
    confidence: Confidence
