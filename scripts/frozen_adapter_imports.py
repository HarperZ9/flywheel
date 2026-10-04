"""The adapter-lane modules the frozen gateway must carry, read from the registry.

An adapter lane (``Lane.adapter_module``, the raw lane today) has no MCP server.
``harness.lanes`` reaches its adapter by name: the roster calls
``import_module(adapter_module).status()`` and an install calls
``import_module(adapter_module + "_install").install()``. PyInstaller cannot
follow an import it only finds in a string, so without these names the frozen
gateway answers ``/api/lanes`` and ``/api/desktop/status`` with an error while a
pip install answers them. That is how the 1.3.3 installer build failed its
frozen smoke with ``RELAY_ROSTER_HTTP``.

The spec adds ``adapter_lane_hidden_imports()`` to its hidden imports. The list
is derived from ``harness.lanes_registry.LANES``, so a new adapter lane is
covered when it is registered. tests/test_frozen_adapter_imports.py checks the
derivation, that each named module exists, and that the spec uses it.
"""
from __future__ import annotations

from typing import Iterable, Mapping


def adapter_modules(lane) -> tuple[str, ...]:
    """The modules ``harness.lanes`` imports by name for one lane."""
    if not getattr(lane, "adapter_module", ""):
        return ()
    return (lane.adapter_module, f"{lane.adapter_module}_install")


def adapter_lane_hidden_imports(lanes: Mapping[str, object] | None = None) -> list[str]:
    """Every adapter-lane module named in the registry, sorted and unique."""
    if lanes is None:
        from harness.lanes_registry import LANES
        lanes = LANES
    names: Iterable[str] = (name for lane in lanes.values()
                            for name in adapter_modules(lane))
    return sorted(set(names))
