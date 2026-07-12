"""Prometheus-compatible metrics endpoint.

Exposes a /metrics route with counters and per-tool latency histograms.
"""

from collections import defaultdict
from typing import Any


class MetricsCollector:
    """Thread-safe in-memory metrics store (no external deps)."""

    def __init__(self):
        import threading
        self._lock = threading.Lock()
        self.total_requests = 0
        self.cache_hits = 0
        self.errors = 0
        self.latency_buckets: dict[str, dict[float, int]] = defaultdict(
            lambda: {0.01: 0, 0.05: 0, 0.1: 0, 0.5: 0, 1.0: 0, 5.0: 0, 10.0: 0, 30.0: 0, float("inf"): 0}
        )
        self.latency_count: dict[str, int] = defaultdict(int)
        self.latency_sum: dict[str, float] = defaultdict(float)

    def record(self, entry: dict[str, Any]):
        with self._lock:
            self.total_requests += 1
            if entry.get("cached"):
                self.cache_hits += 1
            if entry.get("error"):
                self.errors += 1
            lat = entry.get("latency_ms", 0) / 1000.0
            tool = entry.get("tool", "unknown")
            self.latency_count[tool] += 1
            self.latency_sum[tool] += lat
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
                cnt = self.latency_count.get(tool, 0)
                total = self.latency_sum.get(tool, 0.0)
                lines.append(f"agentgate_latency_seconds_{safe}_count {cnt}")
                lines.append(f"agentgate_latency_seconds_{safe}_sum {round(total, 3)}")
        return "\n".join(lines) + "\n"
