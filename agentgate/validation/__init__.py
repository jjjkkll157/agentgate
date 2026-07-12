"""Structured error responses and JSON Schema validation."""

import json
from typing import Any


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


def validate_input(params: dict, schema: dict | None) -> dict | None:
    """Check input against a JSON Schema subset.  Returns error dict or None."""
    if schema is None:
        return None
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    for key in required:
        if key not in params:
            return format_error("schema_violation", f"missing required parameter: {key!r}")
    for key, val in params.items():
        prop = properties.get(key, {})
        expected = prop.get("type")
        if expected == "string" and not isinstance(val, str):
            return format_error("schema_violation", f"{key!r}: expected string, got {type(val).__name__}")
        if expected == "integer" and not isinstance(val, int):
            return format_error("schema_violation", f"{key!r}: expected integer, got {type(val).__name__}")
        if expected == "number" and not isinstance(val, (int, float)):
            return format_error("schema_violation", f"{key!r}: expected number, got {type(val).__name__}")
        if expected == "boolean" and not isinstance(val, bool):
            return format_error("schema_violation", f"{key!r}: expected boolean, got {type(val).__name__}")
    return None


def validate_output(data: dict, schema: dict | None) -> dict | None:
    """Check output against a JSON Schema subset.  Returns error dict or None."""
    if schema is None:
        return None
    required = schema.get("required", [])
    for key in required:
        if key not in data:
            return format_error("schema_violation", f"response missing required field: {key!r}")
    return None
