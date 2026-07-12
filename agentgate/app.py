"""FastAPI application — the proxy server."""

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse

from agentgate.config import Config
from agentgate.core.pipeline import Pipeline
from agentgate.cache import Cache
from agentgate.dashboard import router as dashboard_router
from agentgate.resilience.health import HealthMonitor
from agentgate.telemetry.request_log import record
from agentgate.telemetry.metrics import MetricsCollector


def create_app(config_path: str) -> FastAPI:
    import time
    cfg = Config(config_path)
    cache = Cache()
    pipeline = Pipeline(cfg, cache=cache)
    client = httpx.AsyncClient()
    metrics = MetricsCollector()
    health_monitor = HealthMonitor(cfg)

    app = FastAPI(title="AgentGate", version="0.1.0", docs_url=None, redoc_url=None)

    @app.on_event("startup")
    async def _startup():
        await health_monitor.start(client)

    @app.on_event("shutdown")
    async def _shutdown():
        await health_monitor.stop()
        await client.aclose()

    app.include_router(dashboard_router)

    @app.get("/health")
    async def health():
        return {"status": "ok", "tools": cfg.list_names()}

    @app.get("/metrics")
    async def metrics_endpoint():
        return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")

    @app.api_route("/tool/{name}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def call_tool(name: str, request: Request):
        if name not in cfg.tools:
            raise HTTPException(status_code=404, detail=f"unknown tool: {name!r}")

        if request.method == "GET":
            params = dict(request.query_params)
        else:
            try:
                params = await request.json()
            except Exception:
                params = {}

        t0 = time.monotonic()
        result = await pipeline.run(name, params, client)
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
