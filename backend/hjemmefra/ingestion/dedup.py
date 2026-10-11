"""Duplicate detection by fingerprint. Re-running an import is idempotent."""
from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

from hjemmefra.domain.offer import NormalizedOffer


def deduplicate(offers: Iterable[NormalizedOffer], existing: Dict[str, NormalizedOffer] | None = None) -> Tuple[List[NormalizedOffer], List[NormalizedOffer]]:
    """Return (new_or_updated, duplicates). `existing` keyed by fingerprint."""
    existing = dict(existing or {})
    fresh: List[NormalizedOffer] = []
    dups: List[NormalizedOffer] = []
    for o in offers:
        if o.fingerprint in existing:
            prev = existing[o.fingerprint]
            # same offer seen again -> refresh verification timestamp only
            if o.last_verified_at > prev.last_verified_at:
                prev.last_verified_at = o.last_verified_at
            dups.append(o)
            continue
        existing[o.fingerprint] = o
        fresh.append(o)
    return fresh, dups
