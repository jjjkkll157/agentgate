"""TTL cache with bounded size, O(1) LRU eviction, async-safe."""

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from typing import Any


class Cache:
    """TTL cache keyed on (tool_name, method, params_json).

    Uses OrderedDict for O(1) insertion-order eviction.  When full,
    the least-recently-used entry is popped.  Expired entries are
    lazily purged on get().  Async-safe via asyncio.Lock.
    """

    DEFAULT_MAX_ENTRIES = 10_000

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES):
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._max = max(max_entries, 1)
        self._lock = asyncio.Lock()

    def _key(self, tool: str, method: str, params: dict) -> str:
        try:
            raw = json.dumps([tool, method, params], sort_keys=True, ensure_ascii=False)
        except (TypeError, ValueError):
            raw = json.dumps([tool, method, str(params)], sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()

    async def get(self, tool: str, method: str, params: dict, ttl: float) -> Any | None:
        if ttl <= 0:
            return None
        k = self._key(tool, method, params)
        async with self._lock:
            entry = self._store.get(k)
            if entry is None:
                return None
            ts, val = entry
            if time.monotonic() - ts > ttl:
                self._store.pop(k, None)
                return None
            self._store.move_to_end(k)
            return val

    async def set(self, tool: str, method: str, params: dict, value: Any):
        k = self._key(tool, method, params)
        async with self._lock:
            if k in self._store:
                self._store.move_to_end(k)
            else:
                if len(self._store) >= self._max:
                    self._store.popitem(last=False)
            self._store[k] = (time.monotonic(), value)

    async def clear(self):
        async with self._lock:
            self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)

    @property
    def max_entries(self) -> int:
        return self._max
