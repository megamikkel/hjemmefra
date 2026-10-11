"""Decoder for Nuxt 3 `__NUXT_DATA__` payloads (devalue format: a flat JSON array where
objects and arrays hold indices into the array). Pure data, no code execution."""
from __future__ import annotations

import json
import re
from typing import Any, Iterator, List, Optional

_TAG = re.compile(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', re.S)
_WRAPPERS = {"Reactive", "ShallowReactive", "Ref", "ShallowRef", "NuxtError"}


def extract_payload(html: str) -> Optional[List[Any]]:
    m = _TAG.search(html)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


class Devalue:
    def __init__(self, data: List[Any], max_depth: int = 40):
        self.data, self.max_depth = data, max_depth
        self._memo: dict = {}

    def resolve(self, idx: int, depth: int = 0) -> Any:
        if not isinstance(idx, int) or idx < 0 or idx >= len(self.data):
            return None
        if idx in self._memo:
            return self._memo[idx]
        if depth > self.max_depth:
            return None
        v = self.data[idx]
        if isinstance(v, dict):
            out: dict = {}
            self._memo[idx] = out  # cycle-safe
            for k, i in v.items():
                out[k] = self.resolve(i, depth + 1)
            return out
        if isinstance(v, list):
            if v and isinstance(v[0], str) and v[0] in _WRAPPERS and len(v) == 2:
                r = self.resolve(v[1], depth + 1)
            elif v and isinstance(v[0], str) and v[0] in ("Date",):
                r = v[1] if len(v) > 1 else None
            elif v and isinstance(v[0], str) and v[0] in ("Set", "Map", "null", "undefined", "EmptyRef", "EmptyShallowRef"):
                r = None
            else:
                r = [self.resolve(i, depth + 1) for i in v]
            self._memo[idx] = r
            return r
        self._memo[idx] = v
        return v

    def objects_with(self, *keys: str) -> Iterator[dict]:
        for i, v in enumerate(self.data):
            if isinstance(v, dict) and all(k in v for k in keys):
                yield self.resolve(i)
