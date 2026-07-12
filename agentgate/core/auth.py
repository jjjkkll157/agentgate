"""API token authentication for protecting tool endpoints.

Configure in tools.yaml under the top-level `auth` key:

    auth:
      enabled: true
      tokens:
        - "sk-prod-abc123"
        - "sk-dev-xyz789"

When enabled, every /tool/* request must include an Authorization header:
    Authorization: Bearer sk-prod-abc123
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("agentgate.auth")


class TokenAuth:
    """Validates bearer tokens against a configured allow-list."""

    def __init__(self, tokens: list[str]):
        self._tokens = set(t.strip() for t in tokens if t.strip())

    @property
    def enabled(self) -> bool:
        return len(self._tokens) > 0

    def validate(self, auth_header: str | None) -> bool:
        """Return True if the header is a valid bearer token."""
        if not self._tokens:
            return True  # no tokens configured → allow all
        if not auth_header:
            return False
        if auth_header.startswith("Bearer "):
            return auth_header[7:] in self._tokens
        return auth_header in self._tokens


def load_auth(raw: dict[str, Any]) -> TokenAuth:
    """Parse auth config from the YAML root dict."""
    auth_cfg = raw.get("auth", {})
    if not auth_cfg.get("enabled", False):
        return TokenAuth([])
    return TokenAuth(auth_cfg.get("tokens", []))
