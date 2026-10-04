"""Retryable, observable job runner (in-process scheduler abstraction).

A production deployment can swap this for Celery/APScheduler/cron; job bodies
are plain callables and idempotent by design (ingestion dedupes by fingerprint)."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from hjemmefra.core.logging import get_logger
from hjemmefra.core.metrics import registry

log = get_logger(__name__)


@dataclass
class JobResult:
    job_name: str
    status: str  # SUCCEEDED | FAILED
    attempts: int
    started_at: datetime
    finished_at: datetime
    error: Optional[str] = None
    summary: Optional[dict] = None


def run_job(name: str, fn: Callable[[], Optional[dict]], max_attempts: int = 3, backoff_seconds: float = 0.0) -> JobResult:
    started = datetime.now(timezone.utc)
    attempts = 0
    error: Optional[str] = None
    while attempts < max_attempts:
        attempts += 1
        try:
            summary = fn()
            registry.inc("job_runs_total", job=name, status="SUCCEEDED")
            log.info("job_succeeded", job=name, attempts=attempts)
            return JobResult(name, "SUCCEEDED", attempts, started, datetime.now(timezone.utc), None, summary)
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
            log.warning("job_attempt_failed", job=name, attempt=attempts, error=error)
            if attempts < max_attempts and backoff_seconds:
                time.sleep(backoff_seconds * (2 ** (attempts - 1)))
    registry.inc("job_runs_total", job=name, status="FAILED")
    return JobResult(name, "FAILED", attempts, started, datetime.now(timezone.utc), error, None)
