"""SaaS control plane — multi-instance management, usage analytics, billing hooks.

Exposed at /admin/ when AGENTGATE_ADMIN=true.

Endpoints:
    GET  /admin/                     - dashboard HTML
    GET  /admin/api/tenants          - list tenants + usage
    GET  /admin/api/usage/{tenant}   - tenant usage details
    POST /admin/api/keys/{tenant}    - provision new API key
    GET  /admin/api/audit            - audit trail
    GET  /admin/api/billing/{tenant} - Stripe billing status
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Request as FastAPIRequest
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter(prefix="/admin")
logger = logging.getLogger("agentgate.admin")

_ADMIN_HTML = (Path(__file__).parent / "static" / "admin.html")


@router.get("/", response_class=HTMLResponse)
async def admin_index():
    if _ADMIN_HTML.exists():
        return _ADMIN_HTML.read_text(encoding="utf-8")
    return """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>AgentGate Admin</title>
<style>body{font-family:system-ui;max-width:900px;margin:40px auto;padding:20px;background:#0d1117;color:#c9d1d9}
.panel{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:20px;margin:16px 0}
h1,h2{color:#58a6ff} .stat{font-size:24px;font-weight:bold;color:#3fb950}
table{width:100%%;border-collapse:collapse} td,th{padding:8px 12px;text-align:left;border-bottom:1px solid #30363d}
</style></head>
<body>
<h1>⚡ AgentGate Admin</h1>
<div class="panel" id="tenants"><h2>Tenants</h2><div id="tenant-list">Loading…</div></div>
<div class="panel" id="audit"><h2>Audit Trail</h2><div id="audit-list">Loading…</div></div>
<div class="panel" id="usage"><h2>Global Usage</h2><div id="usage-stats"></div></div>
<script>
async function load() {
  try {
    const t = await fetch('/admin/api/tenants').then(r=>r.json());
    const a = await fetch('/admin/api/audit').then(r=>r.json());
    document.getElementById('tenant-list').innerHTML = Object.entries(t.tenants||{}).map(([id,t])=>
      `<div style="margin:8px 0">${id}: ${t.daily_used}/${t.daily_limit} daily, ${t.monthly_used}/${t.monthly_limit} monthly, scopes: ${t.scopes.join(',')}</div>`
    ).join('') || 'No tenants configured';
    document.getElementById('audit-list').innerHTML = (a.audit||[]).slice(-10).reverse().map(e=>
      `<div style="margin:4px 0;font-size:13px;color:#8b949e">${e.ts} — ${e.action} ${e.tool||''} ${e.tenant||''}</div>`
    ).join('') || 'No audit events';
    const s = await fetch('/dashboard/api/stats').then(r=>r.json());
    document.getElementById('usage-stats').innerHTML = `<span class="stat">${s.total_requests}</span> requests, ${s.errors} errors`;
  } catch(e) { document.body.innerHTML += '<p style="color:red">' + e + '</p>'; }
}
load();
setInterval(load, 10000);
</script></body></html>"""


@router.get("/api/tenants")
async def api_tenants(request: FastAPIRequest):
    from agentgate.tenant import tenant_manager
    return JSONResponse({"tenants": tenant_manager.list_tenants()})


@router.get("/api/audit")
async def api_audit(limit: int = 50):
    from agentgate.core.enterprise_auth import audit_entries
    return JSONResponse({"audit": audit_entries(limit)})


@router.post("/api/keys/{tenant_id}")
async def api_provision_key(tenant_id: str):
    import uuid
    new_key = "sk-" + uuid.uuid4().hex[:24]
    from agentgate.tenant import tenant_manager
    from agentgate.core.enterprise_auth import audit_event
    # Register the new key for the tenant (in-memory only for now)
    tc = tenant_manager._tenants.get(tenant_id)
    if tc is None:
        return JSONResponse({"error": True, "reason": "not_found", "detail": f"unknown tenant: {tenant_id!r}"}, status_code=404)
    tenant_manager._key_to_tenant[new_key] = tenant_id
    audit_event("provision_key", tenant=tenant_id)
    return JSONResponse({"api_key": new_key, "tenant": tenant_id})


@router.get("/api/usage/{tenant_id}")
async def api_usage(tenant_id: str):
    from agentgate.tenant import tenant_manager
    tc = tenant_manager._tenants.get(tenant_id)
    if tc is None:
        return JSONResponse({"error": True, "reason": "not_found", "detail": f"unknown tenant: {tenant_id!r}"}, status_code=404)
    return JSONResponse({
        "tenant": tenant_id,
        "daily_used": tc.daily_used, "daily_limit": tc.daily_limit,
        "monthly_used": tc.monthly_used, "monthly_limit": tc.monthly_limit,
        "scopes": list(tc.scopes) if tc.scopes else ["*"],
    })
