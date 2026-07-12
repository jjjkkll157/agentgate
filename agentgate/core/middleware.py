"""Per-tool callbacks injected into the request pipeline.

Users register hooks in tools.yaml under `middleware.before` / `middleware.after`.
Each hook is a dotted Python path (e.g. "myproject.hooks.log_request") that points
to an async callable with signature:

    async def hook(params: dict, context: dict) -> dict:
        # mutate params/context, return (possibly modified) params
        return params
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable, Awaitable

Hook = Callable[[dict, dict], Awaitable[dict]]

logger = logging.getLogger("agentgate.middleware")


def resolve_hook(path: str) -> Hook:
    """Import a hook from a dotted path like 'mypkg.hooks.my_func'."""
    if "." not in path:
        raise ValueError(f"invalid hook path: {path!r} (expected 'module.function')")
    mod_path, func_name = path.rsplit(".", 1)
    try:
        mod = importlib.import_module(mod_path)
    except ImportError as e:
        raise ImportError(f"cannot import middleware module {mod_path!r}: {e}") from e
    func = getattr(mod, func_name, None)
    if func is None:
        raise AttributeError(f"{mod_path!r} has no attribute {func_name!r}")
    if not callable(func):
        raise TypeError(f"{path!r} is not callable")
    return func


async def run_hooks(hooks: list[Hook], params: dict, context: dict) -> dict:
    """Run a list of hooks sequentially, each receiving and returning params."""
    for hook in hooks:
        try:
            params = await hook(params, context)
        except Exception:
            logger.exception("middleware hook %s failed", getattr(hook, "__name__", hook))
            # hooks failing should not break the request — skip and continue
    return params
