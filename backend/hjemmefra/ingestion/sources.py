"""Build the configured live adapters from settings (compliance-classified, see ADR-0005)."""
from __future__ import annotations

from typing import List, Optional

from hjemmefra.config import Settings
from hjemmefra.ingestion.adapters.salling import SallingFoodWasteAdapter
from hjemmefra.ingestion.adapters.tjek import TjekOffersAdapter
from hjemmefra.ingestion.base import SourceAdapter
from hjemmefra.location.geo import POSTAL_CENTROIDS


def configured_adapters(cfg: Settings, postal_code: Optional[str] = None) -> List[SourceAdapter]:
    postal = postal_code or cfg.source_postal_code
    out: List[SourceAdapter] = []
    if not postal:
        return out
    if cfg.salling_api_token:
        out.append(SallingFoodWasteAdapter(cfg.salling_api_token, postal))
    if cfg.tjek_api_key and postal in POSTAL_CENTROIDS:
        lat, lon = POSTAL_CENTROIDS[postal]
        out.append(TjekOffersAdapter(cfg.tjek_api_key, lat, lon, cfg.source_radius_m, postal))
    return out
