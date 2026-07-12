"""OpenTelemetry tracing for pipeline stages.

Usage:
    from agentgate.telemetry.tracing import Tracer
    Tracer.init(service_name="agentgate", otlp_endpoint="http://localhost:4317")

    with Tracer.start("tool_call") as span:
        span.set_attribute("tool.name", "web_search")
"""

import contextlib
import logging
from typing import Any

logger = logging.getLogger("agentgate.tracing")

import threading
_SPANS: list[dict] = []
_SPAN_LOCK = threading.Lock()


class _NoopSpan:
    def set_attribute(self, k, v): pass
    def set_status(self, code, desc=""): pass
    def record_exception(self, exc): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass


class _InMemSpan:
    def __init__(self, name: str):
        self.name = name
        self.attrs: dict[str, Any] = {}
        self.status = "ok"
        self.start_ns = 0

    def set_attribute(self, k, v):
        self.attrs[k] = v

    def set_status(self, code, desc=""):
        self.status = ("error", desc) if code != 0 else ("ok", desc)

    def record_exception(self, exc):
        self.attrs["exception"] = str(exc)

    def __enter__(self):
        import time
        self.start_ns = time.monotonic_ns()
        return self

    def __exit__(self, *a):
        import time
        dur = (time.monotonic_ns() - self.start_ns) / 1e6
        self.attrs["duration_ms"] = round(dur, 2)
        with _SPAN_LOCK:
            _SPANS.append({"name": self.name, "attrs": self.attrs, "status": self.status})
            if len(_SPANS) > 500:
                _SPANS[:] = _SPANS[-200:]


class Tracer:
    """Singleton tracer factory."""

    _enabled = False

    @classmethod
    def init(cls, service_name: str = "agentgate", otlp_endpoint: str = ""):
        if otlp_endpoint:
            try:
                from opentelemetry import trace
                from opentelemetry.sdk.trace import TracerProvider
                from opentelemetry.sdk.resources import Resource
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
                from opentelemetry.sdk.trace.export import BatchSpanProcessor

                provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
                exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
                provider.add_span_processor(BatchSpanProcessor(exporter))
                trace.set_tracer_provider(provider)
                cls._enabled = True
                logger.info("OTLP tracing enabled → %s", otlp_endpoint)
            except ImportError:
                logger.warning("opentelemetry packages not installed; tracing disabled")
            except Exception as exc:
                logger.warning("OTLP init failed: %s; tracing disabled", exc)

    @classmethod
    def start(cls, name: str) -> Any:
        if not cls._enabled:
            return _InMemSpan(name)
        try:
            from opentelemetry import trace
            return trace.get_tracer(__name__).start_as_current_span(name)
        except Exception:
            return _NoopSpan()

    @classmethod
    def flush_spans(cls) -> list[dict]:
        with _SPAN_LOCK:
            return list(_SPANS)


# ── convenience wrapper for pipeline instrumentation ──

@contextlib.contextmanager
def trace_stage(stage_name: str, tool: str = "", request_id: str = ""):
    """Context manager that records a pipeline stage as a span."""
    span = Tracer.start(stage_name)
    if tool:
        span.set_attribute("tool.name", tool)
    if request_id:
        span.set_attribute("request_id", request_id)
    try:
        yield
    except Exception as exc:
        span.record_exception(exc)
        span.set_status(1, str(exc))
        raise
