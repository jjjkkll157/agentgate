"""Tenant-aware rate limiter, circuit breaker, and quota manager."""

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any

logger = logging.getLogger("agentgate.tenant")


class TenantContext:
    """Per-tenant isolation context — keyed by API key prefix."""
    __slots__ = ("tenant_id", "scopes", "daily_limit", "daily_used",
                 "monthly_limit", "monthly_used", "rate_limiter", "breaker")

    def __init__(self, tenant_id: str, scopes: set[str], daily: int = 0, monthly: int = 0):
        self.tenant_id = tenant_id
        self.scopes = scopes
        self.daily_limit = daily
        self.daily_used = 0
        self.monthly_limit = monthly
        self.monthly_used = 0
        self.rate_limiter = None  # injected externally
        self.breaker = None       # injected externally

    def check_scope(self, tool_name: str) -> bool:
        if not self.scopes or "*" in self.scopes:
            return True
        return tool_name in self.scopes

    def check_quota(self) -> bool:
        if self.daily_limit and self.daily_used >= self.daily_limit:
            return False
        if self.monthly_limit and self.monthly_used >= self.monthly_limit:
            return False
        return True

    def consume(self):
        self.daily_used += 1
        self.monthly_used += 1


class TenantManager:
    """Owns all tenant contexts and routes API keys to them."""

    def __init__(self):
        self._tenants: dict[str, TenantContext] = {}
        self._key_to_tenant: dict[str, str] = {}  # api_key → tenant_id
        self._lock = asyncio.Lock()

    def register(self, tenant_id: str, api_keys: list[str],
                 scopes: list[str] | None = None,
                 daily_limit: int = 0, monthly_limit: int = 0):
        """Register a tenant with one or more API keys."""
        tc = TenantContext(tenant_id, set(scopes or []), daily_limit, monthly_limit)
        self._tenants[tenant_id] = tc
        for key in api_keys:
            self._key_to_tenant[key] = tenant_id
        logger.info("registered tenant %s (keys=%d scopes=%s daily=%d monthly=%d)",
                     tenant_id, len(api_keys), scopes, daily_limit, monthly_limit)

    def resolve(self, api_key: str) -> TenantContext | None:
        """Look up the tenant for an API key."""
        tenant_id = self._key_to_tenant.get(api_key)
        if tenant_id is None:
            return None
        return self._tenants.get(tenant_id)

    def list_tenants(self) -> dict[str, dict[str, Any]]:
        return {
            tid: {
                "scopes": list(tc.scopes) if tc.scopes else ["*"],
                "daily_limit": tc.daily_limit,
                "daily_used": tc.daily_used,
                "monthly_limit": tc.monthly_limit,
                "monthly_used": tc.monthly_used,
            }
            for tid, tc in self._tenants.items()
        }


# singleton
tenant_manager = TenantManager()


def load_tenants(raw: dict) -> TenantManager:
    """Parse `tenants:` section from config YAML."""
    tenants_cfg = raw.get("tenants", {})
    for tenant_id, cfg in tenants_cfg.items():
        if not isinstance(cfg, dict):
            continue
        tenant_manager.register(
            tenant_id=tenant_id,
            api_keys=cfg.get("api_keys", []),
            scopes=cfg.get("scopes"),
            daily_limit=cfg.get("daily_limit", 0),
            monthly_limit=cfg.get("monthly_limit", 0),
        )
    return tenant_manager
