"""Small HTTP client wrapper: timeouts, bounded retries, no secret leakage in errors."""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

import httpx

from hjemmefra.ingestion.base import SourceUnavailable

Fetcher = Callable[[str, Dict[str, str], Dict[str, Any]], Any]


def http_get_json(url: str, headers: Dict[str, str], params: Dict[str, Any], timeout: float = 20.0, retries: int = 2) -> Any:
    last = None
    for attempt in range(retries + 1):
        try:
            r = httpx.get(url, headers=headers, params=params, timeout=timeout, follow_redirects=True)
            if r.status_code == 429 or r.status_code >= 500:
                last = f"HTTP {r.status_code}"
            elif r.status_code >= 400:
                raise SourceUnavailable(f"HTTP {r.status_code} from {url}")
            else:
                return r.json()
        except (httpx.HTTPError, ValueError) as exc:
            last = f"{type(exc).__name__}"
        if attempt < retries:
            time.sleep(0.5 * (2 ** attempt))
    raise SourceUnavailable(f"{last} from {url}")


def http_get_text(url: str, headers: Dict[str, str], timeout: float = 20.0) -> str:
    try:
        r = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise SourceUnavailable(f"{type(exc).__name__} from {url}")
    if r.status_code >= 400:
        raise SourceUnavailable(f"HTTP {r.status_code} from {url}")
    return r.text
