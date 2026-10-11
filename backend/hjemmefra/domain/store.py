from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class OfferScope(str, Enum):
    NATIONAL = "NATIONAL"
    REGIONAL = "REGIONAL"
    LOCAL = "LOCAL"
    STORE = "STORE"


class Chain(BaseModel):
    chain_id: str
    name: str
    membership_program_id: Optional[str] = None


class Store(BaseModel):
    store_id: str
    chain_id: str
    name: str
    address: Optional[str] = None
    postal_code: str
    region: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    opening_hours: Optional[dict] = None


class StoreDistance(BaseModel):
    store: Store
    distance_km: float
    distance_method: str  # "STRAIGHT_LINE_APPROX" | "ROUTED"
