"""Read a lane's live MCP surface from its pinned source.

The generator materializes the pinned package (or its reviewed slice), puts it
and any Studio dependencies first on ``sys.path``, imports the serving module
and asks its own handler for ``tools/list``. Split out of ``_lane_payload_row.py``
for the 300-line gate.

Serving conventions the frozen dispatcher accepts: a ``serve`` callable, or
``serve_stdio`` (forum). The tool list comes from a module-level
``handle_request`` or ``handle`` function, or from the ``handle`` method of the
module's MCP surface class (forum's ``McpSurface``), sync or async.
"""
from __future__ import annotations

import asyncio
import importlib
import inspect
import shutil
import sys
from pathlib import Path
from typing import Any

from _lane_payload_source import GeneratorError, _materialize, _mcp_module, _purge_modules

SERVE_NAMES = ("serve", "serve_stdio")
TOOLS_LIST = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}


def _health_doctor(tool_names: list[str]) -> tuple[str, str]:
    status = next((t for t in tool_names if t.endswith(".status")), None)
    doctor = next((t for t in tool_names if t.endswith(".doctor")), None)
    if not status or not doctor:
        raise GeneratorError(
            f"lane exposes no status/doctor health tools (tools={tool_names!r})"
        )
    return status, doctor


def _handler(module: Any, module_name: str) -> Any:
    # Older lanes name the JSON-RPC dispatcher handle_request; newer lane
    # releases (relay 0.2, plexus 0.2, canon 0.2) name it handle. forum keeps it
    # on its McpSurface class, whose tools/list answer reads module constants
    # only, so an instance built without __init__ answers it without a ledger.
    handler = getattr(module, "handle_request", None) or getattr(module, "handle", None)
    if callable(handler):
        return handler
    classes = [obj for obj in vars(module).values()
               if inspect.isclass(obj) and obj.__module__ == module.__name__
               and callable(getattr(obj, "handle", None))]
    if len(classes) == 1:
        return getattr(classes[0].__new__(classes[0]), "handle")
    raise GeneratorError(
        f"MCP module {module_name!r} has no 'handle_request' or 'handle' tools/list "
        "handler (bundled-lane convention)"
    )


def _tool_surface(module: Any, module_name: str) -> tuple[list[str], str, str]:
    """Read (static_tool_names, callable, callable_style) from an MCP module."""
    serve_name = next((n for n in SERVE_NAMES if callable(getattr(module, n, None))), None)
    if serve_name is None:
        raise GeneratorError(
            f"MCP module {module_name!r} has no 'serve' callable (bundled-lane convention)"
        )
    response = _handler(module, module_name)(dict(TOOLS_LIST))
    if inspect.isawaitable(response):
        response = asyncio.run(response)
    try:
        tool_names = [tool["name"] for tool in response["result"]["tools"]]
    except (TypeError, KeyError) as exc:
        raise GeneratorError(
            f"MCP module {module_name!r} tools/list returned no tool list: {response!r}"
        ) from exc
    serve = getattr(module, serve_name)
    style = "async" if inspect.iscoroutinefunction(serve) else "sync"
    return tool_names, serve_name, style


def _import_serving_module(module_name: str, pkg: str) -> tuple[Any, str]:
    try:
        return importlib.import_module(module_name), module_name
    except ModuleNotFoundError as exc:
        # A `<command> mcp` lane may serve from <pkg>.local_mcp (canon 0.2).
        fallback = f"{pkg}.local_mcp"
        if exc.name != module_name or module_name != f"{pkg}.mcp":
            raise GeneratorError(f"MCP module {module_name!r} import failed: {exc!r}") from exc
        try:
            return importlib.import_module(fallback), fallback
        except Exception as exc2:  # noqa: BLE001 - report the real import failure
            raise GeneratorError(
                f"MCP module {module_name!r} missing and {fallback!r} import failed: {exc2!r}"
            ) from exc2
    except Exception as exc:  # noqa: BLE001 - report the real import failure
        raise GeneratorError(f"MCP module {module_name!r} import failed: {exc!r}") from exc


def mcp_block(checkout: Path, rev: str, lane: Any, pkg: str, pkg_dir: str, *,
              keep: list[str] | None = None,
              extra_root: Path | None = None, extra_pkgs: tuple[str, ...] = ()) -> dict[str, Any]:
    """Import the pinned lane source and read its live MCP surface."""
    tmp = _materialize(checkout, rev, pkg_dir, keep)
    import_root = str(tmp / pkg_dir.rsplit("/", 1)[0]) if "/" in pkg_dir else str(tmp)
    roots = [import_root, *([str(extra_root)] if extra_root else [])]
    purge = (pkg, *extra_pkgs)
    sys.path[:0] = roots
    for name in purge:
        _purge_modules(name)
    try:
        module, module_name = _import_serving_module(_mcp_module(lane, pkg), pkg)
        tool_names, serve_name, style = _tool_surface(module, module_name)
    finally:
        for root in roots:
            while root in sys.path:
                sys.path.remove(root)
        for name in purge:
            _purge_modules(name)
        shutil.rmtree(tmp, ignore_errors=True)
    health, doctor = _health_doctor(tool_names)
    contract = (
        "async_coroutine_runtime_dispatch"
        if style == "async"
        else "compatible_with_sync_dispatcher"
    )
    return {
        "callable": serve_name,
        "callable_style": style,
        "contract_status": contract,
        "doctor_tool": doctor,
        "health_tool": health,
        "module": module_name,
        "static_tool_names": tool_names,
    }
