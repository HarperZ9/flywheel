"""relay_bridge.py — thin bridge to the relay submodule.

Resolves relay's import path (source checkout or frozen build) and exposes
the two relay entry points: ``remote`` (MCP server) and ``agent`` (local
coding agent). The CLI dispatcher in cli_entry delegates here so
cli_entry stays under the line gate.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _ensure_importable() -> bool:
    """Put relay/src/ on sys.path so ``import relay`` resolves.

    In a frozen build PyInstaller already bundled the modules; in a source
    checkout the relay git submodule lives at <repo>/relay/src/relay/."""
    try:
        import relay as _relay  # noqa: F401
        return True
    except ImportError:
        pass
    here = Path(__file__).resolve().parent.parent
    src = here / "relay" / "src"
    if (src / "relay" / "__init__.py").exists():
        sys.path.insert(0, str(src))
        return True
    return False


_NOT_FOUND = ("relay submodule not found; run "
              "`git submodule update --init` from the repo root")


def cmd_remote(_argv: list[str]) -> int:
    """`flywheel remote` — start the relay remote MCP server."""
    if not _ensure_importable():
        print(_NOT_FOUND, file=sys.stderr)
        return 1
    from relay.remote_cli import main as _remote_main
    return _remote_main()


def cmd_relay(argv: list[str]) -> int:
    """`flywheel relay` — run the relay local coding agent."""
    if not _ensure_importable():
        print(_NOT_FOUND, file=sys.stderr)
        return 1
    from relay.local_agent_cli import main as _relay_main
    return _relay_main(argv)
