"""Lane child modes of the frozen engine executable.

A frozen engine cannot run ``python -m <module>`` (the executable refuses
``-m``), and a clean machine has no lane console scripts on PATH. Two lane
surfaces therefore run as fixed modes of the engine itself:

``--lane-mcp writing``
    The Writing Workspace MCP server, pinned to the Flywheel home, so a tool
    argument naming another home is refused (HOME_MISMATCH). The import of
    ``writing_mcp`` below is static, so the freeze carries the module.

``--bundled-lane-cli <lane> <args...>``
    A payload lane's CLI, for the native screens (feeds, science bench,
    discourse, workspace map). Only the subcommands in ``LANE_CLIS``,
    ``--version`` and ``index router-job --help`` pass; the lane then clears
    the same descriptor admission as ``--bundled-lane-mcp``. stdout and stderr
    are switched to UTF-8 first, since a pipe on Windows otherwise encodes
    with the code page and a non-ASCII feed title raises.

Each dispatcher returns None for an argv that is not its mode, 2 for a
malformed one, and the child's exit code otherwise.
"""
from __future__ import annotations

import importlib
import os
import re
import sys
from typing import Callable

from .bundled_lane_admission import admit_bundled_lane
from .lane_workdir import flywheel_home

LANE_MCP_FLAG = "--lane-mcp"
LANE_CLI_FLAG = "--bundled-lane-cli"
_SAFE_LANE = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
# lane -> (CLI module, callable, subcommands the native screens run)
LANE_CLIS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "gather": ("gather.cli", "main", ("feed", "arxiv")),
    "crucible": ("crucible.cli", "main", ("assess",)),
    "chorus": ("chorus.cli", "main", ("run", "corpora", "digests")),
    "index": ("index_graph.cli", "main", ("map", "graph", "symbols")),
}
# Whole argvs allowed besides a listed subcommand: the version check every CLI
# answers, and the index router-job capability probe (index_jobs._probe_engine).
EXACT_ARGVS: dict[str, tuple[tuple[str, ...], ...]] = {
    "index": (("router-job", "--help"),),
}


def _serve_writing() -> int:
    from . import writing_mcp
    return int(writing_mcp.serve(operator_home=str(flywheel_home(os.environ))) or 0)


LANE_MCP_SERVERS: dict[str, Callable[[], int]] = {"writing": _serve_writing}


def dispatch_lane_mcp(argv: list[str]) -> int | None:
    """Serve ``--lane-mcp <lane>`` for a lane in ``LANE_MCP_SERVERS``."""
    if not argv or argv[0] != LANE_MCP_FLAG:
        return None
    if len(argv) != 2 or argv[1] not in LANE_MCP_SERVERS:
        return 2
    return LANE_MCP_SERVERS[argv[1]]()


def cli_args_allowed(lane: str, args: list[str]) -> bool:
    """True when ``args`` is a listed subcommand, ``--version`` or an exact argv."""
    if lane not in LANE_CLIS or not args:
        return False
    if tuple(args) == ("--version",) or tuple(args) in EXACT_ARGVS.get(lane, ()):
        return True
    return args[0] in LANE_CLIS[lane][2]


def utf8_stdio() -> None:
    """Switch stdout and stderr to UTF-8; a stream that cannot switch is left."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (ValueError, OSError):
            continue


def dispatch_bundled_lane_cli(argv: list[str]) -> int | None:
    """Run ``--bundled-lane-cli <lane> <args...>`` after admission."""
    if not argv or argv[0] != LANE_CLI_FLAG:
        return None
    if len(argv) < 3 or not _SAFE_LANE.fullmatch(argv[1]):
        return 2
    lane, args = argv[1], list(argv[2:])
    if not cli_args_allowed(lane, args):
        return 2
    admission = admit_bundled_lane(lane, executable=sys.executable, environ=os.environ)
    if admission.blocking_codes:
        return 2
    utf8_stdio()
    module_name, callable_name, _subcommands = LANE_CLIS[lane]
    try:
        main = getattr(importlib.import_module(module_name), callable_name)
    except (ImportError, AttributeError):
        return 2
    try:
        return int(main(args) or 0)
    except SystemExit as exit_:
        code = exit_.code
        return code if isinstance(code, int) else (0 if code is None else 1)
