"""In-process request log for the dashboard."""

import time
from collections import deque
from typing import Any


_MAX_ENTRIES = 500

_log: deque[dict[str, Any]] = deque(maxlen=_MAX_ENTRIES)


def record(entry: dict[str, Any]):
    entry.setdefault("ts", time.strftime("%H:%M:%S"))
    _log.append(entry)


def recent(limit: int = 50) -> list[dict[str, Any]]:
    items = list(_log)
    return items[-limit:]


def clear():
    _log.clear()
