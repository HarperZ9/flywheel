"""Installed launcher for the stateful Writing Workspace MCP server.

The module route ``python -m harness.writing_mcp`` keeps its historical
behavior for source checkouts and tests. This installed console command is the
portable cross-harness surface and therefore refuses to start unless the
operator has selected an explicit Flywheel state home.
"""

from __future__ import annotations

import os
import sys

from . import writing_mcp


REQUIRED_ENV = "FLYWHEEL_HOME"
EX_USAGE = 64
_UNRESOLVED_HOME_VALUES = frozenset({
    "${FLYWHEEL_HOME}",
    "$FLYWHEEL_HOME",
    "%FLYWHEEL_HOME%",
})


def _explicit_home() -> bool:
    value = os.environ.get(REQUIRED_ENV, "").strip()
    return bool(value) and value not in _UNRESOLVED_HOME_VALUES


def _startup_home() -> str:
    return os.path.abspath(os.path.expanduser(os.environ[REQUIRED_ENV].strip()))


def main(stdin=None, stdout=None, stderr=None) -> int:
    stderr = stderr or sys.stderr
    if not _explicit_home():
        stderr.write(
            "FLYWHEEL_HOME is required for flywheel-writing-workspace-mcp; "
            "set it to an operator-owned Flywheel state directory before "
            "starting the installed Writing Workspace MCP server.\n"
        )
        return EX_USAGE
    return writing_mcp.serve(stdin=stdin, stdout=stdout, operator_home=_startup_home())


if __name__ == "__main__":
    raise SystemExit(main())
