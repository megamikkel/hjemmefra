"""Locality engine: filter stores by distance with least-necessary precision.

Distance is a STRAIGHT_LINE_APPROX (haversine) multiplied by a documented
detour factor, never presented as routed driving distance. A routing adapter
can replace `DistanceProvider` later without touching the optimizer.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol, Sequence, Tuple

from hjemmefra.domain.household import Location
from hjemmefra.domain.store import Store, StoreDistance

# Danish postal code centroids (subset; extend via data file). lat, lon
POSTAL_CENTROIDS: Dict[str, Tuple[float, float]] = {
    "8000": (56.1567, 10.2108),  # Aarhus C
    "8200": (56.1870, 10.1800),  # Aarhus N
    "8210": (56.1700, 10.1500),  # Aarhus V
    "8230": (56.1550, 10.1200),  # Åbyhøj
    "8240": (56.2000, 10.2200),  # Risskov
    "2100": (55.7050, 12.5750),  # København Ø
    "2200": (55.6950, 12.5500),  # København N
    "5000": (55.3959, 10.3883),  # Odense C
    "9000": (57.0488, 9.9217),  # Aalborg
    "4200": (55.4027, 11.3546),  # Slagelse
}

ROAD_DETOUR_FACTOR = 1.3  # straight-line -> rough road distance; documented approximation


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class DistanceProvider(Protocol):
    def distance(self, origin: Location, store: Store) -> Optional[StoreDistance]: ...


class ApproxDistanceProvider:
    """Haversine × detour factor. method = STRAIGHT_LINE_APPROX."""

    def _coords(self, postal_code: str, lat: Optional[float], lon: Optional[float]) -> Optional[Tuple[float, float]]:
        if lat is not None and lon is not None:
            return lat, lon
        return POSTAL_CENTROIDS.get(postal_code)

    def distance(self, origin: Location, store: Store) -> Optional[StoreDistance]:
        o = self._coords(origin.postal_code, origin.lat, origin.lon)
        s = self._coords(store.postal_code, store.lat, store.lon)
        if o is None or s is None:
            return None
        km = haversine_km(o[0], o[1], s[0], s[1]) * ROAD_DETOUR_FACTOR
        return StoreDistance(store=store, distance_km=round(km, 2), distance_method="STRAIGHT_LINE_APPROX")


def filter_stores(origin: Location, stores: Sequence[Store], max_distance_km: float,
                  selected_store_ids: Sequence[str] = (), provider: Optional[DistanceProvider] = None) -> List[StoreDistance]:
    provider = provider or ApproxDistanceProvider()
    out: List[StoreDistance] = []
    for s in stores:
        if selected_store_ids and s.store_id not in selected_store_ids:
            continue
        d = provider.distance(origin, s)
        if d is None:
            if selected_store_ids:  # explicitly selected: keep with unknown distance
                out.append(StoreDistance(store=s, distance_km=max_distance_km, distance_method="UNKNOWN"))
            continue
        if d.distance_km <= max_distance_km or s.store_id in selected_store_ids:
            out.append(d)
    return sorted(out, key=lambda d: (d.distance_km, d.store.store_id))
