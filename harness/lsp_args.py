"""lsp_args.py -- what the LSP command accepts, kept apart from what it does.

Three subcommands take the same eleven flags, because all three start a server
and hand it a file. Writing that list once is the point of this module: a flag
that means one thing under `ask` and something slightly different under
`diagnostics` is a bug a reader has to find by comparing two parsers.

Nothing here imports the handlers. The parser records which subcommand was
named and the command looks up its own function, so the flags can be read, and
tested, without starting anything.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .lsp_operations import OPERATIONS

__all__ = ["build_parser"]


def _shared(parser: argparse.ArgumentParser) -> None:
    """The flags every subcommand that talks to a server needs."""
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=None,
                        help="the workspace root. Defaults to here.")
    parser.add_argument("--language", default="python",
                        help="the language id the server is told, e.g. rust.")
    parser.add_argument("--log-dir", type=Path, default=None,
                        help="write the run's action log here. Without it the "
                             "run leaves no receipt.")
    parser.add_argument("--run-id", default=None,
                        help="name the run. Defaults to the time it started.")
    parser.add_argument("--transcript", type=Path, default=None,
                        help="keep what each digest was taken over, here. It "
                             "holds the file's contents verbatim.")
    parser.add_argument("--keep-bytes", action="store_true",
                        help="keep the transcript beside the log, under the "
                             "log directory.")
    parser.add_argument("--timeout", type=float, default=30.0,
                        help="seconds to wait for one request.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("server", nargs="+",
                        help="the language server to start, after a bare --")


def _ask(sub) -> None:
    parser = sub.add_parser("ask", allow_abbrev=False,
                              help="ask about one position in one file")
    _shared(parser)
    parser.add_argument("--operation", default="definition",
                        choices=sorted(OPERATIONS))
    parser.add_argument("--line", type=int, default=0)
    parser.add_argument("--character", type=int, default=0,
                        help="the index into the line as Python counts it. It "
                             "is converted to the encoding the two sides "
                             "agreed on before it is sent.")
    parser.add_argument("--strict", action="store_true",
                        help="refuse here if the server never advertised the "
                             "request, rather than sending it anyway.")
    parser.add_argument("--new-name", default="",
                        help="what rename renames to. Read by no other "
                             "operation, and not sent by them either.")
    parser.add_argument("--query", default="",
                        help="what workspace_symbols searches for.")


def _diagnostics(sub) -> None:
    parser = sub.add_parser("diagnostics", allow_abbrev=False,
                            help="what the server says is wrong with a file")
    _shared(parser)
    parser.add_argument("--wait", type=float, default=5.0,
                        help="seconds to wait for a server that indexes before "
                             "it publishes.")


def _verify(sub) -> None:
    parser = sub.add_parser("verify", allow_abbrev=False,
                              help="recheck a run's log offline")
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--transcript", type=Path, default=None,
                        help="the bytes the log's digests were taken over. "
                             "Without it the answer is UNVERIFIABLE.")
    parser.add_argument("--json", action="store_true")


def build_parser(description: str) -> argparse.ArgumentParser:
    """The whole command line, with abbreviation off.

    Argparse takes any unambiguous prefix of a flag by default. A near-miss of
    a flag that decides what gets written to disk has to be a usage error.
    """
    parser = argparse.ArgumentParser(prog="flywheel lsp", allow_abbrev=False,
                                     description=description)
    parser.add_argument("--limits", action="store_true",
                        help="print what an LSP run record does not prove.")
    sub = parser.add_subparsers(dest="command")
    _ask(sub)
    _diagnostics(sub)
    _verify(sub)
    return parser
