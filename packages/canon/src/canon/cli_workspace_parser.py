"""Argument parsing for `canon workspace ...`, `canon handoff` and `canon switch`.

Kept apart from cli_parser.py so the older command surface stays as it was.
Every workspace subcommand shares three options: the workspace directory, the
store root, and a remote override for the project identity.
"""
from __future__ import annotations

import argparse

from .cli_parser import describe


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", default=".", help="a directory inside the project")
    parser.add_argument("--store", default=None,
                        help="store root (default: CANON_STORE or ~/.canon/store)")
    parser.add_argument("--remote", default=None,
                        help="use this remote URL for the project identity")


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{text!r} is not a whole number") from exc
    if value < 1:
        raise argparse.ArgumentTypeError("a budget must be 1 or more")
    return value


def _budget_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--to", required=True,
                        help="claude-code, codex, gemini-cli, cursor, copilot or markdown")
    parser.add_argument("--budget-bytes", type=_positive_int, default=None,
                        help="override the brief byte budget")
    parser.add_argument("--budget-lines", type=_positive_int, default=None,
                        help="override the brief line budget")
    parser.add_argument("--include-project", action="append", default=[],
                        help="also read this project's records (named, labelled)")


def add_handoff_args(parser: argparse.ArgumentParser) -> None:
    add_common(parser)
    _budget_args(parser)
    parser.add_argument("--out", default=None, help="write the brief to this new file")
    parser.add_argument("--receipt", default=None, help="write the receipt to this new file")


def add_switch_args(parser: argparse.ArgumentParser) -> None:
    add_common(parser)
    _budget_args(parser)
    parser.add_argument("--dry-run", action="store_true", help="plan and print; write nothing")
    parser.add_argument("--create", action="store_true",
                        help="create the instruction file if it does not exist")
    parser.add_argument("--receipt", default=None,
                        help="write the switch receipt, which names every left-out record, "
                             "to this new file")
    parser.add_argument("--home", default=None, help="home directory for global surfaces")


def _inherit(child: argparse.ArgumentParser, parent: argparse.ArgumentParser) -> None:
    child._canon_stdout = parent._canon_stdout  # type: ignore[attr-defined]
    child._canon_stderr = parent._canon_stderr  # type: ignore[attr-defined]


def add_workspace_args(parser: argparse.ArgumentParser) -> None:
    subs = parser.add_subparsers(dest="ws_command", metavar="workspace-command",
                                 required=True)
    for name, help_text, adder in _SUBCOMMANDS:
        child = subs.add_parser(name, help=help_text, description=describe(help_text))
        _inherit(child, parser)
        add_common(child)
        adder(child)


def _no_args(parser: argparse.ArgumentParser) -> None:
    return None


def _list_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--proposed", action="store_true", help="list proposed records")
    parser.add_argument("--kind", default=None, help="only this record kind")


def _promote_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("record_id", help="the accepted record to promote")
    parser.add_argument("--reason", required=True, help="why it applies to every project")


def _adopt_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--from", dest="from_project", required=True,
                        help="the project id whose accepted records to copy here")
    parser.add_argument("--reason", required=True, help="why these records belong here")


def _focus_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--goal", required=True, help="what the project is doing now")
    parser.add_argument("--area", action="append", default=[], help="an active file or area")
    parser.add_argument("--branch", default=None, help="branch (default: read from HEAD)")
    parser.add_argument("--notes", default=None, help="anything the next tool should know")


def _task_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("title", help="the work item")
    parser.add_argument("--status", default="open", help="open, in-progress, blocked, done, dropped")
    parser.add_argument("--detail", default=None, help="more about the work item")


def _set_status_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("record_id", help="the work item id, for example task-3")
    parser.add_argument("status", help="open, in-progress, blocked, done, dropped")
    parser.add_argument("--detail", default=None, help="replace the detail text")


def _decide_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--title", required=True, help="the decision in a few words")
    parser.add_argument("--decision", required=True, help="what was decided")
    parser.add_argument("--context", required=True, help="why it came up")
    parser.add_argument("--status", default="accepted", help="proposed, accepted, superseded, rejected")
    parser.add_argument("--reject", nargs=2, action="append", default=[],
                        metavar=("OPTION", "REASON"), help="an alternative and why it was dropped")


def _constraint_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("statement", help="the constraint or quirk")
    parser.add_argument("--quirk", action="store_true", help="a quirk of the environment")
    parser.add_argument("--reason", default=None, help="why it holds")
    parser.add_argument("--applies-to", action="append", default=[], help="a path it applies to")


def _import_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--from", dest="source_format", required=True,
                        help="claude-code (session .jsonl) or codex (rollout .jsonl)")
    parser.add_argument("path", help="the session file to read")
    parser.add_argument("--accept-foreign-source", action="store_true",
                        help="import even when the source names another project")
    parser.add_argument("--drop-type", action="append", default=[],
                        help="declare the drop of content the importer does not know")
    parser.add_argument("--dry-run", action="store_true", help="report; write nothing")


def _pull_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--from", dest="target", required=True,
                        help="the target whose instruction region to read back")
    parser.add_argument("--home", default=None, help="home directory for global surfaces")
    parser.add_argument("--dry-run", action="store_true", help="report; write nothing")


def _decide_proposal_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("record_id", help="the proposed record id")
    parser.add_argument("--reason", default=None, help="why (required to reject)")
    parser.add_argument("--force", action="store_true",
                        help="accept even when the accepted record changed since the proposal")


_SUBCOMMANDS = (
    ("id", "show this project's identity", _no_args),
    ("list", "list this project's records", _list_args),
    ("promote", "move a record to global scope (logged)", _promote_args),
    ("adopt", "copy another project's records here (logged)", _adopt_args),
    ("focus", "set what the project is doing now", _focus_args),
    ("task", "add a work item", _task_args),
    ("set-status", "change a work item's status", _set_status_args),
    ("decide", "record a decision and the alternatives dropped", _decide_args),
    ("constraint", "record a constraint or an environment quirk", _constraint_args),
    ("targets", "list the handoff targets, their files, budgets and downgrades", _no_args),
    ("import", "propose records from a Claude Code or Codex session", _import_args),
    ("pull", "turn edits made inside a rendered region into proposals", _pull_args),
    ("accept", "accept a proposed record", _decide_proposal_args),
    ("reject", "reject a proposed record (logged)", _decide_proposal_args),
)
