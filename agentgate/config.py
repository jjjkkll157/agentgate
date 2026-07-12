"""Tool configuration: load, validate, and resolve tools.yaml."""

import os
import re
from pathlib import Path
from typing import Any

import yaml


_ENV_VAR_RE = re.compile(r"\$\{(\w+)\}")

_DEFAULT_SCHEMA = {
    "retry": {"max_attempts": 3, "backoff": "exponential", "initial_delay": 1.0, "max_delay": 60.0},
    "ratelimit": {"max_per_minute": 60, "strategy": "wait"},
    "circuit_breaker": {"failure_threshold": 5, "cooldown_seconds": 30},
    "concurrency": {"max_concurrent": 0},  # 0 = unlimited
    "health": {},                          # no health check by default
    "timeout": 30.0,
    "cache": {"ttl_seconds": 0},
    "fallback": [],
    "middleware": {"before": [], "after": []},
}


def _interpolate_env(value: Any) -> Any:
    """Replace ${VAR} patterns in strings with environment variable values."""
    if isinstance(value, str):
        def _replace(m):
            return os.environ.get(m.group(1), m.group(0))
        return _ENV_VAR_RE.sub(_replace, value)
    if isinstance(value, dict):
        return {k: _interpolate_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate_env(v) for v in value]
    return value


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. override wins on conflict."""
    result = base.copy()
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


class ToolConfig:
    """A single tool's configuration after resolution."""

    def __init__(self, name: str, raw: dict):
        self.name = name
        if "endpoint" not in raw:
            raise ValueError(f"tool {name!r}: missing required field 'endpoint'")
        self.endpoint = raw["endpoint"]
        self.method = raw.get("method", "POST").upper()
        self.headers = raw.get("headers", {})
        self.params = raw.get("params", {})
        self.body_template = raw.get("body_template", {})
        self.retry = raw.get("retry", _DEFAULT_SCHEMA["retry"])
        self.ratelimit = raw.get("ratelimit", _DEFAULT_SCHEMA["ratelimit"])
        self.circuit_breaker = raw.get("circuit_breaker", _DEFAULT_SCHEMA["circuit_breaker"])
        self.timeout = raw.get("timeout", _DEFAULT_SCHEMA["timeout"])
        self.cache = raw.get("cache", _DEFAULT_SCHEMA["cache"])
        self.fallback = raw.get("fallback", _DEFAULT_SCHEMA["fallback"])
        self.concurrency = raw.get("concurrency", _DEFAULT_SCHEMA["concurrency"])
        self.health = raw.get("health", _DEFAULT_SCHEMA["health"])
        self.middleware = raw.get("middleware", _DEFAULT_SCHEMA["middleware"])
        self.schema_in = raw.get("schema", {}).get("input")
        self.schema_out = raw.get("schema", {}).get("output")
        self.description = raw.get("description", "")

    def __repr__(self):
        return f"ToolConfig({self.name!r}, {self.method} {self.endpoint})"


class Config:
    """Loaded configuration: all registered tools."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.tools: dict[str, ToolConfig] = {}
        self._load()

    def _load(self):
        raw_text = self.path.read_text(encoding="utf-8")
        raw = yaml.safe_load(raw_text) or {}
        raw_tools = raw.get("tools", raw)  # tolerate both "tools:" top-level and bare

        if isinstance(raw_tools, dict):
            for name, tool_def in raw_tools.items():
                if not isinstance(tool_def, dict):
                    continue
                merged = _deep_merge(_DEFAULT_SCHEMA, tool_def)
                merged = _interpolate_env(merged)
                self.tools[name] = ToolConfig(name, merged)

    def get(self, name: str) -> ToolConfig:
        cfg = self.tools.get(name)
        if cfg is None:
            raise KeyError(f"unknown tool: {name!r} (registered: {list(self.tools)})")
        return cfg

    def list_names(self) -> list[str]:
        return list(self.tools)
