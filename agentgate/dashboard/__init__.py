"""Dashboard API router — log search, replay, breaker status."""

from fastapi import APIRouter, Query, Request as FastAPIRequest
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pathlib import Path

router = APIRouter(prefix="/dashboard")
_STATIC = Path(__file__).parent / "static"


def _static_file(filename: str) -> str:
    return (_STATIC / filename).read_text(encoding="utf-8")


@router.get("/", response_class=HTMLResponse)
async def index():
    return _static_file("index.html")


@router.get("/style.css")
async def style():
    return Response(content=_static_file("style.css"), media_type="text/css")


# ── log search ──────────────────────────────────────────────

@router.get("/api/log")
async def api_log(
    limit: int = Query(50, ge=1, le=500),
    tool: str = Query(None),
    error_only: bool = Query(False),
    q: str = Query(None),
):
    from agentgate.telemetry.request_log import recent
    entries = recent(500)
    if tool:
        entries = [e for e in entries if e.get("tool") == tool]
    if error_only:
        entries = [e for e in entries if e.get("error")]
    if q:
        ql = q.lower()
        entries = [e for e in entries if ql in e.get("tool", "").lower()
                   or ql in e.get("error", "").lower()]
    return JSONResponse(entries[-limit:])


# ── replay ───────────────────────────────────────────────────

@router.post("/api/replay/{index}")
async def api_replay(index: int, request: FastAPIRequest):
    from agentgate.telemetry.request_log import recent
    items = list(recent(500))
    if index < 0 or index >= len(items):
        return JSONResponse({"error": True, "reason": "bad_index", "detail": f"index {index} out of range [0, {len(items)-1}]"}, status_code=400)
    entry = items[index]
    tool_name = entry.get("tool", "")
    if not tool_name:
        return JSONResponse({"error": True, "reason": "no_tool"}, status_code=400)

    pipeline = getattr(request.app.state, "pipeline", None)
    client = getattr(request.app.state, "http_client", None)
    if not pipeline or not client:
        return JSONResponse({"error": True, "reason": "not_ready"}, status_code=503)

    try:
        result = await pipeline.run(tool_name, {}, client)
        return JSONResponse(result)
    except Exception as exc:
        return JSONResponse({"error": True, "reason": "replay_failed", "detail": str(exc)}, status_code=502)


# ── breaker control ─────────────────────────────────────────

@router.get("/api/breakers")
async def api_breakers(request: FastAPIRequest):
    pipeline = getattr(request.app.state, "pipeline", None)
    if not pipeline:
        return JSONResponse({"error": True, "reason": "not_ready"}, status_code=503)
    states = {name: {"state": b.state.value, "retry_after": round(b.retry_after(), 1)}
              for name, b in pipeline._breakers.items()}
    return JSONResponse({"breakers": states})


@router.post("/api/breakers/{name}/reset")
async def api_breaker_reset(name: str, request: FastAPIRequest):
    pipeline = getattr(request.app.state, "pipeline", None)
    if not pipeline:
        return JSONResponse({"error": True, "reason": "not_ready"}, status_code=503)
    breaker = pipeline._breakers.get(name)
    if breaker is None:
        return JSONResponse({"error": True, "reason": "not_found", "detail": f"no breaker for {name!r}"}, status_code=404)
    breaker._state = type(breaker._state)("closed")
    breaker._failure_count = 0
    breaker._probe_active = False
    return JSONResponse({"ok": True, "tool": name, "state": breaker.state.value})


# ── stats ───────────────────────────────────────────────────

@router.get("/api/stats")
async def api_stats():
    from agentgate.telemetry.request_log import recent
    entries = recent(500)
    total = len(entries)
    errors = sum(1 for e in entries if e.get("error"))
    tool_counts: dict[str, int] = {}
    for e in entries:
        t = e.get("tool", "unknown")
        tool_counts[t] = tool_counts.get(t, 0) + 1
    avg_latency = sum(e.get("latency_ms", 0) for e in entries) / max(total, 1)
    return JSONResponse({
        "total_requests": total,
        "errors": errors,
        "error_rate": round(errors / max(total, 1), 3),
        "avg_latency_ms": round(avg_latency, 1),
        "tools": tool_counts,
    })
