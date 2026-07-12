"""Structured error responses that an AI agent can parse."""

import json


def format_error(
    reason: str,
    detail: str = "",
    retry_after: float = 0,
    circuit_open: bool = False,
    raw_body: str = "",
    status_code: int = 0,
) -> dict:
    """Build a stable error dict the agent can rely on.

    Never returns a raw HTML body — agents choke on those.
    """
    err = {
        "error": True,
        "reason": reason,
        "detail": detail,
    }
    if retry_after > 0:
        err["retry_after"] = round(retry_after, 1)
    if circuit_open:
        err["circuit_open"] = True
    if raw_body and len(raw_body) < 500:
        err["raw_snippet"] = raw_body[:500]
    if status_code:
        err["status"] = status_code
    return err


def format_success(data: dict, cached: bool = False, attempt: int = 1) -> dict:
    """Wrap a successful response so the agent can inspect metadata."""
    return {
        "error": False,
        "data": data,
        "cached": cached,
        "attempt": attempt,
    }
