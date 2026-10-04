"""Canonical product resolver (entity resolution with confidence).

Strategy (deterministic, explainable):
 1. exact alias match (normalized)            -> HIGH
 2. all alias tokens contained in title       -> HIGH/MEDIUM depending on extra tokens
 3. token overlap >= threshold                -> MEDIUM/LOW
 4. negative aliases block a match (e.g. "hel kylling" must not match CHICKEN_BREAST)
LOW matches are never used automatically for pricing.
An LLM may *suggest* mappings which land in the review queue; it is not the authority.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from hjemmefra.core.confidence import MatchConfidence
from hjemmefra.domain.product import CanonicalProduct

_STOP = {"og", "med", "i", "af", "pr", "ca", "stk", "pk", "ps", "g", "kg", "ml", "l", "cl", "dl", "frit", "valg", "flere", "varianter"}


def norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = re.sub(r"[^a-z0-9æøåäöü ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(s: str) -> List[str]:
    return [t for t in norm_text(s).split() if t not in _STOP and not t.isdigit()]


@dataclass
class ResolveResult:
    canonical_id: Optional[str]
    confidence: MatchConfidence
    explanation: str
    score: float = 0.0


class ProductResolver:
    def __init__(self, products: Iterable[CanonicalProduct], negative_aliases: Optional[Dict[str, List[str]]] = None):
        self.products: Dict[str, CanonicalProduct] = {p.canonical_id: p for p in products}
        self.negative: Dict[str, List[str]] = {k: [norm_text(x) for x in v] for k, v in (negative_aliases or {}).items()}
        self._alias_index: Dict[str, str] = {}
        for p in self.products.values():
            for a in [p.name, *p.aliases]:
                self._alias_index[norm_text(a)] = p.canonical_id

    def get(self, canonical_id: str) -> Optional[CanonicalProduct]:
        return self.products.get(canonical_id)

    def resolve(self, title: str) -> ResolveResult:
        t = norm_text(title)
        if not t:
            return ResolveResult(None, MatchConfidence.UNMATCHED, "empty title")
        if t in self._alias_index:
            cid = self._alias_index[t]
            return ResolveResult(cid, MatchConfidence.HIGH, f"exact alias match '{t}'", 1.0)

        title_tokens = set(tokens(title))
        best: Optional[ResolveResult] = None
        for p in self.products.values():
            if any(neg in t for neg in self.negative.get(p.canonical_id, [])):
                continue
            for alias in [p.name, *p.aliases]:
                at = set(tokens(alias))
                if not at:
                    continue
                # alias fully contained in title (phrase) -> strong
                if norm_text(alias) in t:
                    extra = len(title_tokens - at)
                    conf = MatchConfidence.HIGH if extra <= 2 else MatchConfidence.MEDIUM
                    cand = ResolveResult(p.canonical_id, conf, f"alias '{alias}' contained in title", 0.9 - 0.05 * extra)
                else:
                    overlap = len(at & title_tokens) / len(at)
                    if overlap < 0.5:
                        continue
                    conf = MatchConfidence.MEDIUM if overlap >= 0.75 else MatchConfidence.LOW
                    cand = ResolveResult(p.canonical_id, conf, f"token overlap {overlap:.2f} with alias '{alias}'", overlap * 0.8)
                if best is None or cand.score > best.score:
                    best = cand
        if best is None:
            return ResolveResult(None, MatchConfidence.UNMATCHED, "no alias overlap")
        return best
