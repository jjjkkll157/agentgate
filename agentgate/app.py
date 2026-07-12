"""FastAPI application — the proxy server with graceful shutdown."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from agentgate.cache import Cache
from agentgate.config import Config
from agentgate.core.auth import load_auth
from agentgate.core.pipeline import Pipeline
from agentgate.dashboard import router as dashboard_router
from agentgate.resilience.health import HealthMonitor
from agentgate.resilience.ratelimit import RateLimiter
from agentgate.telemetry.metrics import MetricsCollector
from agentgate.telemetry.request_log import record

logger = logging.getLogger("agentgate")

_INFLIGHT: set[asyncio.Task] = set()
_DRAINING = False


def create_app(config_path: str) -> FastAPI:
    import time

    raw_text = Path(config_path).read_text(encoding="utf-8")
    raw = yaml.safe_load(raw_text) or {}
    cfg = Config(config_path)
    auth = load_auth(raw)

    cache = Cache()
    pipeline = Pipeline(cfg, cache=cache)
    client = httpx.AsyncClient()
    metrics = MetricsCollector()
    health_monitor = HealthMonitor(cfg)
    health_monitor._breakers = pipeline._breakers
    global_limiter = RateLimiter(max_per_minute=6000)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global _DRAINING
        await health_monitor.start(client)
        yield
        # ── graceful shutdown ──
        _DRAINING = True
        logger.info("draining %d in-flight requests …", len(_INFLIGHT))
        if _INFLIGHT:
            await asyncio.gather(*_INFLIGHT, return_exceptions=True)
        await health_monitor.stop()
        await client.aclose()
        _DRAINING = False

    app = FastAPI(title="AgentGate", version="0.2.0", docs_url=None, redoc_url=None, lifespan=lifespan)

    # ── expose shared state for dashboard routes ──
    app.state.pipeline = pipeline
    app.state.http_client = client
    app.state.config = cfg
    app.state.cache = cache

    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.include_router(dashboard_router)

    # ── endpoints ────────────────────────────────────────────

    @app.get("/health")
    async def health():
        return {
            "status": "draining" if _DRAINING else "ok",
            "version": "0.2.0",
            "tools": cfg.list_names(),
            "breakers": {n: b.state.value for n, b in pipeline._breakers.items()},
            "monitor_running": health_monitor.running,
            "in_flight": len(_INFLIGHT),
        }

    @app.get("/version")
    async def version():
        return {"version": "0.2.0", "project": "AgentGate"}

    @app.get("/metrics")
    async def metrics_endpoint():
        return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")

    @app.api_route("/tool/{name}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def call_tool(name: str, request: Request):
        import uuid as _uuid
        req_id = _uuid.uuid4().hex[:12]

        if _DRAINING:
            return JSONResponse(
                {"error": True, "reason": "shutting_down", "detail": "server is draining", "request_id": req_id},
                status_code=503,
            )

        if not await global_limiter.acquire():
            return JSONResponse(
                {"error": True, "reason": "global_rate_limit", "detail": "server overloaded", "request_id": req_id},
                status_code=429,
            )

        if auth.enabled and not auth.validate(request.headers.get("Authorization")):
            return JSONResponse(
                {"error": True, "reason": "unauthorized", "detail": "invalid or missing token", "request_id": req_id},
                status_code=401,
            )

        if name not in cfg.tools:
            return JSONResponse(
                {"error": True, "reason": "unknown_tool", "detail": f"unknown tool: {name!r}", "request_id": req_id},
                status_code=404,
            )

        if request.method == "GET":
            params = dict(request.query_params)
        else:
            try:
                body = await request.json()
                params = body if isinstance(body, dict) else {}
            except Exception:
                params = {}

        t0 = time.monotonic()
        try:
            result = await pipeline.run(name, params, client)
        except Exception as exc:
            logger.exception("unhandled pipeline error tool=%s", name)
            return JSONResponse(
                {"error": True, "reason": "internal_error", "detail": str(exc), "request_id": req_id},
                status_code=502,
            )
        latency_ms = (time.monotonic() - t0) * 1000

        entry = {
            "tool": name,
            "status": result.get("status", 200 if not result.get("error") else 0),
            "error": result.get("reason", ""),
            "latency_ms": round(latency_ms, 1),
            "cached": result.get("cached", False),
        }
        record(entry)
        metrics.record(entry)

        return JSONResponse(content=result, status_code=200)

    return app
