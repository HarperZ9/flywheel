"""Argument handling for the stdio MCP servers started with `python -m`.

`python -m canon.local_mcp` and `python -m canon.context_mcp` read JSON-RPC
from stdin until it closes. Before this, both called `serve()` straight from
their `__main__` block, so `--help` started a server that sat waiting on stdin
and an unknown argument was ignored. Parsing argv first means `--help` and
`--version` print and exit 0 without serving, and an unknown argument exits 2
with argparse's message on stderr.
"""
from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence

from ._version import __version__


def run_server(
    *,
    module: str,
    server_name: str,
    description: str,
    serve: Callable[[], int],
    argv: Sequence[str] | None = None,
) -> int:
    """Parse argv for a server module, then serve only when nothing else was asked."""
    parser = argparse.ArgumentParser(prog=f"python -m {module}", description=description)
    parser.add_argument("-V", "--version", action="version",
                        version=f"{server_name} {__version__}",
                        help="print the installed version and exit")
    parser.parse_args(argv)
    return serve()


__all__ = ["run_server"]
