"""Minimal in-process metrics registry.

Acts as a hook point: a Prometheus/OpenTelemetry exporter can read
`registry.snapshot()`. Keeps counters and simple histograms (count/sum/max).
"""
from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Tuple

LabelKey = Tuple[Tuple[str, str], ...]


def _key(labels: Dict[str, str]) -> LabelKey:
    return tuple(sorted(labels.items()))


@dataclass
class Histogram:
    count: int = 0
    total: float = 0.0
    maximum: float = 0.0

    def observe(self, v: float) -> None:
        self.count += 1
        self.total += v
        self.maximum = max(self.maximum, v)

    @property
    def mean(self) -> float:
        return self.total / self.count if self.count else 0.0


@dataclass
class MetricsRegistry:
    counters: Dict[str, Dict[LabelKey, int]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))
    histograms: Dict[str, Dict[LabelKey, Histogram]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(Histogram)))
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def inc(self, name: str, value: int = 1, **labels: str) -> None:
        with self._lock:
            self.counters[name][_key(labels)] += value

    def observe(self, name: str, value: float, **labels: str) -> None:
        with self._lock:
            self.histograms[name][_key(labels)].observe(value)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "counters": {n: {str(dict(k)): v for k, v in d.items()} for n, d in self.counters.items()},
                "histograms": {
                    n: {str(dict(k)): {"count": h.count, "sum": h.total, "max": h.maximum, "mean": h.mean} for k, h in d.items()}
                    for n, d in self.histograms.items()
                },
            }

    def reset(self) -> None:
        with self._lock:
            self.counters.clear()
            self.histograms.clear()


registry = MetricsRegistry()

# Metric names used across the codebase (kept here for discoverability).
OFFERS_INGESTED = "offers_ingested_total"
OFFERS_VALIDATION = "offers_validation_total"  # labels: status
OFFERS_DEDUPED = "offers_deduplicated_total"
PRODUCT_MATCH = "product_match_total"  # labels: confidence
OPTIMIZER_RUNTIME = "optimizer_runtime_seconds"  # labels: mode, status
PLAN_GENERATION = "plan_generation_total"  # labels: status
CANDIDATE_COUNT = "candidate_count"
LOW_CONFIDENCE_PRICE_USED = "low_confidence_price_used_total"
SOURCE_FRESHNESS = "source_freshness_seconds"  # labels: source
