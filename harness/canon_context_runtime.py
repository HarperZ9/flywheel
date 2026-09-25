"""Runtime selection for the private Canon context MCP child."""
from __future__ import annotations

from pathlib import Path
import sys

CANON_CONTEXT_DB = "CANON_CONTEXT_DB"
CANON_CONTEXT_SCOPE = "CANON_CONTEXT_SCOPE"
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
    return lane_process_environment(
        "canon", {CANON_CONTEXT_DB: db, CANON_CONTEXT_SCOPE: TRUSTED_SCOPE}, environ=env)
