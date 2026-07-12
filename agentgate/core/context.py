"""Per-request metadata carrier."""

import time
import uuid
from dataclasses import dataclass, field


@dataclass
class RequestContext:
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    tool_name: str = ""
    start_time: float = field(default_factory=time.monotonic)
    attempt: int = 1
    status_code: int = 0
    error: str = ""
    latency_ms: float = 0.0
    cached: bool = False

    def finish(self):
        self.latency_ms = (time.monotonic() - self.start_time) * 1000
