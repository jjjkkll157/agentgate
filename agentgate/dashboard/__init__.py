"""Dashboard API router — log search, replay, breaker control, SSE stream, export."""

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Query, Request as FastAPIRequest
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

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


# ── SSE stream ───────────────────────────────────────────────

@router.get("/api/stream")
async def api_stream(request: FastAPIRequest):
    """Server-Sent Events — push each new request log entry in real time."""

    async def _generator():
        from agentgate.telemetry.request_log import recent, _MAX_ENTRIES
        seen = max(0, len(recent(_MAX_ENTRIES)) - 1)
        while True:
            if await request.is_disconnected():
                break
            entries = recent(_MAX_ENTRIES)
            new_entries = entries[seen:]
            for entry in new_entries:
                yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"
            seen = len(entries)
            await asyncio.sleep(1.0)

    return StreamingResponse(_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


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


# ── export ───────────────────────────────────────────────────

@router.get("/api/log/export")
async def api_log_export(format: str = Query("json", pattern="^(json|csv)$")):
    """Download full log as JSON or CSV."""
    from agentgate.telemetry.request_log import recent
    entries = recent(500)
    if format == "csv":
        import csv, io
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=["ts", "tool", "status", "error", "latency_ms", "cached"])
        w.writeheader()
        for e in entries:
            w.writerow({k: e.get(k, "") for k in w.fieldnames})
        return Response(buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=agentgate-log.csv"})
    return JSONResponse(entries)


# ── replay ───────────────────────────────────────────────────

@router.post("/api/replay/{index}")
async def api_replay(index: int, request: FastAPIRequest):
    from agentgate.telemetry.request_log import recent
    items = list(recent(500))
    if index < 0 or index >= len(items):
        return JSONResponse({"error": True, "reason": "bad_index",
                             "detail": f"index {index} out of range [0, {len(items)-1}]"}, status_code=400)
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
        return JSONResponse({"error": True, "reason": "not_found",
                             "detail": f"no breaker for {name!r}"}, status_code=404)
    await breaker.reset()
    return JSONResponse({"ok": True, "tool": name, "state": breaker.state.value})


# ── tool management ─────────────────────────────────────────

@router.post("/api/tools/{name}/disable")
async def api_tool_disable(name: str, request: FastAPIRequest):
    config = getattr(request.app.state, "config", None)
    if not config:
        return JSONResponse({"error": True, "reason": "not_ready"}, status_code=503)
    try:
        tool = config.get(name)
    except KeyError:
        return JSONResponse({"error": True, "reason": "not_found",
                             "detail": f"unknown tool: {name!r}"}, status_code=404)
    tool._disabled = True
    return JSONResponse({"ok": True, "tool": name, "disabled": True})


@router.post("/api/tools/{name}/enable")
async def api_tool_enable(name: str, request: FastAPIRequest):
    config = getattr(request.app.state, "config", None)
    if not config:
        return JSONResponse({"error": True, "reason": "not_ready"}, status_code=503)
    try:
        tool = config.get(name)
    except KeyError:
        return JSONResponse({"error": True, "reason": "not_found",
                             "detail": f"unknown tool: {name!r}"}, status_code=404)
    tool._disabled = False
    return JSONResponse({"ok": True, "tool": name, "disabled": False})


# ── stats ───────────────────────────────────────────────────

@router.get("/api/stats")
async def api_stats():
    from agentgate.telemetry.request_log import recent
    entries = recent(500)
    total = len(entries)
    errors = sum(1 for e in entries if e.get("error"))
    tool_counts: dict[str, int] = {}
    latencies = [e.get("latency_ms", 0) for e in entries if e.get("latency_ms")]
    for e in entries:
        t = e.get("tool", "unknown")
        tool_counts[t] = tool_counts.get(t, 0) + 1
    avg_latency = sum(latencies) / max(len(latencies), 1)
    sorted_lat = sorted(latencies)
    n = len(sorted_lat)

    def _pct(p):
        if n == 0:
            return 0
        idx = int(n * p / 100)
        return round(sorted_lat[min(idx, n - 1)], 1)

    return JSONResponse({
        "total_requests": total,
        "errors": errors,
        "error_rate": round(errors / max(total, 1), 3),
        "avg_latency_ms": round(avg_latency, 1),
        "p50_ms": _pct(50),
        "p90_ms": _pct(90),
        "p99_ms": _pct(99),
        "tools": tool_counts,
    })
