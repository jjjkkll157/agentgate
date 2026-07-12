"""FastAPI application — the proxy server."""

import httpx
import logging
import yaml
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from agentgate.config import Config
from agentgate.core.pipeline import Pipeline
from agentgate.core.auth import TokenAuth, load_auth
from agentgate.resilience.ratelimit import RateLimiter
from agentgate.cache import Cache
from agentgate.dashboard import router as dashboard_router
from agentgate.resilience.health import HealthMonitor
from agentgate.telemetry.request_log import record
from agentgate.telemetry.metrics import MetricsCollector

logger = logging.getLogger("agentgate")


def create_app(config_path: str) -> FastAPI:
    import time

    # Load config once; reuse raw dict for auth parsing
    from pathlib import Path as _Path
    raw_text = _Path(config_path).read_text(encoding="utf-8")
    raw = yaml.safe_load(raw_text) or {}
    cfg = Config(config_path)
    auth = load_auth(raw)

    cache = Cache()
    pipeline = Pipeline(cfg, cache=cache)
    client = httpx.AsyncClient()
    metrics = MetricsCollector()
    health_monitor = HealthMonitor(cfg)
    health_monitor._breakers = pipeline._breakers

    # global rate limiter for the entire proxy (100 req/s by default)
    global_limiter = RateLimiter(max_per_minute=6000)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await health_monitor.start(client)
        yield
        await health_monitor.stop()
        await client.aclose()

    app = FastAPI(title="AgentGate", version="0.1.0", docs_url=None, redoc_url=None, lifespan=lifespan)

    # CORS: allow localhost-originated requests (browser-based tools)
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(dashboard_router)

    @app.get("/health")
    async def health():
        breaker_states = {
            name: b.state.value
            for name, b in pipeline._breakers.items()
        }
        return {
            "status": "ok",
            "version": "0.1.0",
            "tools": cfg.list_names(),
            "breakers": breaker_states,
            "monitor_running": health_monitor.running,
        }

    @app.get("/version")
    async def version():
        return {"version": "0.1.0", "project": "AgentGate"}

    @app.get("/metrics")
    async def metrics_endpoint():
        return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")

    @app.api_route("/tool/{name}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def call_tool(name: str, request: Request):
        import uuid as _uuid
        req_id = _uuid.uuid4().hex[:12]

        # global rate limit
        if not await global_limiter.acquire():
            return JSONResponse(
                {"error": True, "reason": "global_rate_limit", "detail": "server overloaded", "request_id": req_id},
                status_code=429,
            )

        # auth check
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
