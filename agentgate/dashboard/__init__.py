"""Dashboard API router — serves the mini web UI."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pathlib import Path

router = APIRouter(prefix="/dashboard")

_STATIC = Path(__file__).parent / "static"


def _read_static(filename: str) -> str:
    return (_STATIC / filename).read_text(encoding="utf-8")


@router.get("/", response_class=HTMLResponse)
async def index():
    return _read_static("index.html")


@router.get("/style.css")
async def style():
    from fastapi.responses import Response
    return Response(content=_read_static("style.css"), media_type="text/css")


@router.get("/api/log")
async def api_log(limit: int = 50):
    from agentgate.telemetry.request_log import recent
    return JSONResponse(recent(limit))


@router.get("/api/stats")
async def api_stats():
    from agentgate.telemetry.request_log import recent
    entries = recent(500)
    total = len(entries)
    errors = sum(1 for e in entries if e.get("error"))
    avg_latency = sum(e.get("latency_ms", 0) for e in entries) / max(total, 1)
    return JSONResponse({
        "total_requests": total,
        "errors": errors,
        "error_rate": round(errors / max(total, 1), 3),
        "avg_latency_ms": round(avg_latency, 1),
    })
