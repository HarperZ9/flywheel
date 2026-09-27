"""Runtime selection for the private Canon context MCP child."""
from __future__ import annotations

from pathlib import Path
import sys

CANON_CONTEXT_DB = "CANON_CONTEXT_DB"
CANON_CONTEXT_SCOPE = "CANON_CONTEXT_SCOPE"
#: canon 0.4.x applies a context purge plan only on a server started with this
#: set to ``apply``. The engine calls health, ingest and query and never starts
#: the context child with it, whatever the environment or an env_allow grant says.
CANON_CONTEXT_MCP_PURGE = "CANON_CONTEXT_MCP_PURGE"
TRUSTED_SCOPE = "trusted-local-process"
PRIVATE_CHILD_ARGV = ("--canon-context-mcp",)
SOURCE_CHILD_ARGV = ("-m", "canon.context_mcp")


def is_frozen_process() -> bool:
    return bool(getattr(sys, "frozen", False))


def context_db_configured(value: str | None) -> bool:
    return isinstance(value, str) and bool(value) and Path(value).is_absolute()


def context_mcp_command(
        executable: str | None = None, *, frozen: bool | None = None) -> list[str]:
    exe = executable or sys.executable
    if is_frozen_process() if frozen is None else frozen:
        return [exe, *PRIVATE_CHILD_ARGV]
    return [exe, *SOURCE_CHILD_ARGV]


def context_mcp_environment(env: dict[str, str], db: str) -> dict[str, str]:
    """The canon lane environment drawn from ``env``, plus the database and scope.

    The child runs the flywheel-canon lane's code, so it gets the lane env
    (lane_env.py), not the caller's whole environment."""
    if not context_db_configured(db):
        raise ValueError("Canon context database path must be absolute")
    from .lane_env import lane_process_environment
    child = lane_process_environment(
        "canon", {CANON_CONTEXT_DB: db, CANON_CONTEXT_SCOPE: TRUSTED_SCOPE}, environ=env)
    return {key: value for key, value in child.items()
            if key.upper() != CANON_CONTEXT_MCP_PURGE}


def context_version_refusal(*, frozen: bool | None = None,
                            installed: str | None = None) -> str | None:
    """``CANON_CONTEXT_OUTDATED`` when a non-frozen engine would run a canon
    older than the lane pin (GHSA-48rq-xjfx-6j4f: before 0.4.2 an MCP ingest
    was stored unredacted and query excerpts were cut before scrubbing). A
    frozen build runs its pinned payload. An unknown version is not judged."""
    if is_frozen_process() if frozen is None else frozen:
        return None
    from .lane_runtime_versions import version_below
    from .lanes_registry import LANES
    if installed is None:
        from . import lane_runtime_support
        installed = lane_runtime_support.installed_version(LANES["canon"])
    if installed and version_below(installed, LANES["canon"].version):
        return "CANON_CONTEXT_OUTDATED"
    return None
