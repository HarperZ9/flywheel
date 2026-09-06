"""dap_args.py -- what the DAP command accepts, kept apart from what it does.

Nothing here imports the handlers. The parser records which subcommand was
named and the command looks up its own function, so the flags can be read, and
tested, without starting a debug adapter.

Two flags in here decide something other than formatting, and they are the
reason this module is worth reading. `--allow-terminal` is the grant: it is the
only way this client will start a process an adapter asked for. `--values` puts
the debuggee's memory on stdout. Both default off, and neither changes what the
record carries.
"""
from __future__ import annotations

import argparse
from pathlib import Path

__all__ = ["breakpoints_from", "build_parser"]


def breakpoints_from(pairs) -> dict:
    """`file:line` arguments folded into the shape the session takes.

    Lines are grouped by file because that is how the protocol sets them: one
    request per source, carrying every line at once. A second request for the
    same file replaces the first, so a caller that sent one breakpoint at a time
    would end up with only the last of them.
    """
    grouped: dict = {}
    for pair in pairs or ():
        text = str(pair)
        path, _, line = text.rpartition(":")
        if not path or not line.strip().isdigit():
            raise ValueError(f"a breakpoint reads as file:line, got {text!r}")
        grouped.setdefault(path, []).append(int(line))
    return grouped


def _run(sub) -> None:
    parser = sub.add_parser("run", allow_abbrev=False,
                              help="debug a program to its first stop")
    parser.add_argument("--program", type=Path, default=None,
                        help="the program to launch under the adapter.")
    parser.add_argument("--attach-pid", type=int, default=None,
                        help="attach to a running process instead of "
                             "launching one. Not both.")
    parser.add_argument("--adapter-id", default="flywheel",
                        help="the client id the adapter is told at initialize.")
    parser.add_argument("--break", dest="breakpoints", action="append",
                        default=[], metavar="FILE:LINE",
                        help="a breakpoint, repeatable.")
    parser.add_argument("--launch-json", default="",
                        help="extra launch or attach arguments as JSON, "
                             "merged over the ones built here. Adapters need "
                             "their own keys and this is where they go.")
    parser.add_argument("--root", type=Path, default=None,
                        help="the directory the adapter runs in. Defaults to "
                             "here, and bounds --allow-terminal.")
    parser.add_argument("--allow-terminal", action="store_true",
                        help="start the process an adapter asks for, inside "
                             "the root. Off, this client starts nothing and "
                             "the refusal goes on the record.")
    parser.add_argument("--values", action="store_true",
                        help="print variable values. They are the debuggee's "
                             "memory. The record carries names either way.")
    parser.add_argument("--stack-levels", type=int, default=20,
                        help="how many frames to read at the stop.")
    parser.add_argument("--wait", type=float, default=30.0,
                        help="seconds to wait for the program to stop.")
    _shared(parser)


def _shared(parser: argparse.ArgumentParser) -> None:
    """The flags about the record and the clock, and the adapter to start."""
    parser.add_argument("--log-dir", type=Path, default=None,
                        help="write the run's action log here. Without it the "
                             "run leaves no receipt.")
    parser.add_argument("--run-id", default=None,
                        help="name the run. Defaults to the time it started.")
    parser.add_argument("--transcript", type=Path, default=None,
                        help="keep what each digest was taken over, here. It "
                             "holds every frame verbatim, values included.")
    parser.add_argument("--keep-bytes", action="store_true",
                        help="keep the transcript beside the log, under the "
                             "log directory.")
    parser.add_argument("--timeout", type=float, default=30.0,
                        help="seconds to wait for one request.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("adapter", nargs="+",
                        help="the debug adapter to start, after a bare --")


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
    a flag that decides whether a process gets started has to be a usage error.

    Every subcommand parser turns it off again. A subparser does not inherit the
    setting, and the flags that decide anything are all on the subcommands, so
    the one on this parser governs `--limits` and nothing else.
    """
    parser = argparse.ArgumentParser(prog="flywheel dap", allow_abbrev=False,
                                     description=description)
    parser.add_argument("--limits", action="store_true",
                        help="print what a DAP run record does not prove.")
    sub = parser.add_subparsers(dest="command")
    _run(sub)
    _verify(sub)
    return parser
