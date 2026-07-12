"""Simple in-memory request result cache with TTL."""

import hashlib
import json
import time
from typing import Any


class Cache:
    """TTL cache keyed on (tool_name, method, params_json)."""

    def __init__(self):
        self._store: dict[str, tuple[float, Any]] = {}

    def _key(self, tool: str, method: str, params: dict) -> str:
        raw = json.dumps([tool, method, params], sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, tool: str, method: str, params: dict, ttl: float) -> Any | None:
        if ttl <= 0:
            return None
        k = self._key(tool, method, params)
        entry = self._store.get(k)
        if entry is None:
            return None
        ts, val = entry
        if time.monotonic() - ts > ttl:
            del self._store[k]
            return None
        return val

    def set(self, tool: str, method: str, params: dict, value: Any):
        k = self._key(tool, method, params)
        self._store[k] = (time.monotonic(), value)

    def clear(self):
        self._store.clear()
