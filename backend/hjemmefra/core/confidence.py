from __future__ import annotations

from enum import Enum


class Confidence(str, Enum):
    VERIFIED = "VERIFIED"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"

    @property
    def rank(self) -> int:
        return {"VERIFIED": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}[self.value]

    def at_least(self, other: "Confidence") -> bool:
        return self.rank >= other.rank


class MatchConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNMATCHED = "UNMATCHED"


def min_confidence(*values: Confidence) -> Confidence:
    return min(values, key=lambda c: c.rank) if values else Confidence.UNKNOWN
