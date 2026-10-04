"""Source adapter interface.

Every data source (API, feed, HTML, PDF, OCR, manual) implements SourceAdapter.
Raw records are stored separately from normalized offers; the normalizer and the
validation pipeline are shared. Each adapter declares a compliance class so a
source is classified BEFORE it is used (requirement 50).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Iterable, List, Optional

from hjemmefra.domain.offer import RawOfferRecord, SourceType


class ComplianceClass(str, Enum):
    OFFICIAL_API = "OFFICIAL_API"
    LICENSED_FEED = "LICENSED_FEED"
    PUBLIC_PAGE = "PUBLIC_PAGE"
    USER_SUPPLIED = "USER_SUPPLIED"
    OTHER = "OTHER"


@dataclass(frozen=True)
class SourceDescriptor:
    source_id: str
    source_type: SourceType
    compliance: ComplianceClass
    retailer: str
    freshness_sla: timedelta = timedelta(days=1)
    terms_reference: Optional[str] = None
    automated_access_allowed: bool = True


@dataclass
class FetchResult:
    descriptor: SourceDescriptor
    records: List[RawOfferRecord] = field(default_factory=list)
    captured_at: Optional[datetime] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


class SourceAdapter(ABC):
    descriptor: SourceDescriptor

    @abstractmethod
    def fetch(self) -> FetchResult:
        """Return raw records. Must never raise for transient source failures;
        report them via FetchResult.error so one failing source does not take
        the pipeline down (graceful degradation)."""


class SourceUnavailable(Exception):
    pass
