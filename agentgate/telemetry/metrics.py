"""Prometheus-compatible metrics endpoint.

Exposes a /metrics route on the dashboard router with counters for
total requests, cache hits, errors, and per-tool latency histograms.
"""

import time
from collections import defaultdict
from typing import Any


class MetricsCollector:
    """Thread-safe in-memory metrics store (no external deps)."""

    def __init__(self):
        self._lock = __import__("threading").Lock()
        self.total_requests = 0
        self.cache_hits = 0
        self.errors = 0
        self.latency_buckets: dict[str, dict[float, int]] = defaultdict(
            lambda: {0.01: 0, 0.05: 0, 0.1: 0, 0.5: 0, 1.0: 0, 5.0: 0, 10.0: 0, 30.0: 0, float("inf"): 0}
        )

    def record(self, entry: dict[str, Any]):
        with self._lock:
            self.total_requests += 1
            if entry.get("cached"):
                self.cache_hits += 1
            if entry.get("error"):
                self.errors += 1
            lat = entry.get("latency_ms", 0) / 1000.0
            tool = entry.get("tool", "unknown")
            buckets = self.latency_buckets[tool]
            for bound in sorted(buckets):
                if lat <= bound:
                    buckets[bound] += 1
                    break

    def render(self) -> str:
        """Produce Prometheus text format."""
        lines = []
        with self._lock:
            lines.append(f"# HELP agentgate_requests_total Total tool requests.\n# TYPE agentgate_requests_total counter\nagentgate_requests_total {self.total_requests}")
            lines.append(f"# HELP agentgate_cache_hits_total Cache hits.\n# TYPE agentgate_cache_hits_total counter\nagentgate_cache_hits_total {self.cache_hits}")
            lines.append(f"# HELP agentgate_errors_total Error responses.\n# TYPE agentgate_errors_total counter\nagentgate_errors_total {self.errors}")
            for tool, buckets in sorted(self.latency_buckets.items()):
                safe = tool.replace("-", "_").replace(".", "_")
                lines.append(f"# HELP agentgate_latency_seconds_{safe} Latency histogram for {tool}.\n# TYPE agentgate_latency_seconds_{safe} histogram")
                for bound, count in sorted(buckets.items()):
                    label = "+Inf" if bound == float("inf") else str(bound)
                    lines.append(f'agentgate_latency_seconds_{safe}_bucket{{le="{label}"}} {count}')
        return "\n".join(lines) + "\n"
