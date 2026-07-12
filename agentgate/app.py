"""FastAPI application — the proxy server."""

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from agentgate.config import Config
from agentgate.core.pipeline import Pipeline
from agentgate.cache import Cache
from agentgate.dashboard import router as dashboard_router
from agentgate.telemetry.request_log import record


def create_app(config_path: str) -> FastAPI:
    import time
    cfg = Config(config_path)
    cache = Cache()
    pipeline = Pipeline(cfg, cache=cache)
    client = httpx.AsyncClient()

    app = FastAPI(title="AgentGate", version="0.1.0", docs_url=None, redoc_url=None)

    @app.on_event("shutdown")
    async def _shutdown():
        await client.aclose()

    app.include_router(dashboard_router)

    @app.get("/health")
    async def health():
        return {"status": "ok", "tools": cfg.list_names()}

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

        return JSONResponse(content=result, status_code=200)

    return app
