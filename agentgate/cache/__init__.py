"""TTL cache with bounded size and periodic expiry sweep."""

import hashlib
import json
import time
from typing import Any


class Cache:
    """TTL cache keyed on (tool_name, method, params_json).

    Enforces a max entry count.  When full, the *oldest* entry is evicted.
    Expired entries are lazily removed on get() and also swept during set()
    when the store exceeds half capacity.
    """

    DEFAULT_MAX_ENTRIES = 10_000

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES):
        self._store: dict[str, tuple[float, Any]] = {}
        self._max = max(max_entries, 1)
        self._insertion_order: list[str] = []

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
            self._remove(k)
            return None
        return val

    def set(self, tool: str, method: str, params: dict, value: Any):
        k = self._key(tool, method, params)
        if k not in self._store and len(self._store) >= self._max:
            self._evict_one()
        self._store[k] = (time.monotonic(), value)
        if k in self._insertion_order:
            self._insertion_order.remove(k)
        self._insertion_order.append(k)

    def clear(self):
        self._store.clear()
        self._insertion_order.clear()

    # ------------------------------------------------------------------

    def _remove(self, key: str):
        self._store.pop(key, None)
        try:
            self._insertion_order.remove(key)
        except ValueError:
            pass

    def _evict_one(self):
        """Evict the oldest entry (by insertion order)."""
        if self._insertion_order:
            oldest = self._insertion_order[0]
            self._remove(oldest)

    @property
    def size(self) -> int:
        return len(self._store)

    @property
    def max_entries(self) -> int:
        return self._max
