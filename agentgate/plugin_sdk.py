"""Plugin SDK — install, discover, and run AgentGate plugins.

Plugin manifest (plugin.yaml):
    name: my-plugin
    version: 1.0.0
    entrypoint: mypackage.plugin:register
    hooks:
      - pre_request
      - post_response
      - on_breaker_trip

Plugin install:
    agentgate plugin install myplugin  # from PyPI
    agentgate plugin install ./local-plugin/
    agentgate plugin list
"""

import importlib
import logging
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("agentgate.plugin")

_HOOKS: dict[str, list[Callable]] = {
    "pre_request": [],
    "post_response": [],
    "on_breaker_trip": [],
    "on_startup": [],
    "on_shutdown": [],
}


def register_hook(hook_name: str, fn: Callable):
    """Register a lifecycle hook callback."""
    if hook_name not in _HOOKS:
        raise ValueError(f"unknown hook: {hook_name!r} (available: {list(_HOOKS)})")
    _HOOKS[hook_name].append(fn)
    logger.debug("plugin registered hook %s → %s", hook_name, getattr(fn, "__name__", fn))


async def fire_hook(hook_name: str, *args, **kwargs):
    """Fire all registered callbacks for a hook."""
    for fn in _HOOKS.get(hook_name, []):
        try:
            result = fn(*args, **kwargs)
            if hasattr(result, "__await__"):
                await result
        except Exception:
            logger.exception("plugin hook %s/%s failed", hook_name, getattr(fn, "__name__", fn))


def discover_plugins(plugins_dir: str | Path = ""):
    """Walk the plugins directory and load all manifests."""
    root = Path(plugins_dir) if plugins_dir else Path(__file__).parent.parent.parent / "plugins"
    if not root.exists():
        return
    for manifest_path in root.rglob("plugin.yaml"):
        try:
            import yaml
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            name = manifest.get("name", manifest_path.parent.name)
            entrypoint = manifest.get("entrypoint", "")
            if entrypoint:
                mod_path, func_name = entrypoint.rsplit(":", 1)
                mod = importlib.import_module(mod_path)
                register_fn = getattr(mod, func_name)
                register_fn()
                logger.info("loaded plugin %s (%s)", name, entrypoint)
        except Exception:
            logger.exception("failed to load plugin at %s", manifest_path)
