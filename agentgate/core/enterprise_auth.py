"""Enterprise authentication — OAuth2/OIDC + mTLS + audit trail.

Supported modes:
    - bearer: static token list (current)
    - oauth2: JWT validation with JWKS endpoint
    - mtls:  client certificate verification (via reverse proxy header)

Audit log records:
    - tool calls (success/failure, tenant, latency)
    - admin actions (disable tool, reset breaker, add/revoke key)
"""

import logging
import time
from collections import deque
from typing import Any

logger = logging.getLogger("agentgate.auth")

# ── audit log ──────────────────────────────────────────────

_audit_log: deque[dict] = deque(maxlen=1000)


def audit_event(action: str, **details):
    entry = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "action": action, **details}
    _audit_log.append(entry)
    logger.info("audit: %s %s", action, details.get("tool", ""))


def audit_entries(limit: int = 50) -> list[dict]:
    items = list(_audit_log)
    return items[-limit:]


# ── OAuth2 / JWT ─────────────────────────────────────────

class JWTAuth:
    """Validate JWT bearer tokens against OIDC provider."""

    def __init__(self, jwks_url: str = "", issuer: str = "", audience: str = ""):
        self._jwks_url = jwks_url
        self._issuer = issuer
        self._audience = audience
        self._keys: list[dict] = []

    async def _fetch_keys(self):
        if not self._jwks_url:
            return
        try:
            import httpx
            async with httpx.AsyncClient() as c:
                resp = await c.get(self._jwks_url, timeout=10)
                self._keys = resp.json().get("keys", [])
        except Exception:
            logger.warning("failed to fetch JWKS from %s", self._jwks_url)

    def validate(self, token: str) -> dict | None:
        """Return claims dict if valid, None otherwise."""
        if not self._jwks_url:
            return None
        try:
            import jwt
            header = jwt.get_unverified_header(token)
            kid = header.get("kid", "")
            key = next((k for k in self._keys if k.get("kid") == kid), None)
            if not key:
                return None
            from jwt.algorithms import RSAAlgorithm
            public_key = RSAAlgorithm.from_jwk(key)
            claims = jwt.decode(token, public_key, algorithms=["RS256"],
                                issuer=self._issuer, audience=self._audience)
            return claims
        except ImportError:
            logger.debug("PyJWT not installed; JWT auth disabled")
        except Exception as exc:
            logger.debug("JWT validation failed: %s", exc)
        return None
