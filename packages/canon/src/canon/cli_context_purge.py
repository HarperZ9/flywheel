"""`canon context purge` and `canon context retention`.

--dry-run prints the plan and its digest. --confirm-plan <digest> applies that
plan only, and refuses when the store has moved past it, so the owner applies
exactly what the dry run showed. --yes prints the plan it computes at run time
and applies it. With none of these the command prints the plan and applies it
only when the owner types the word "purge".

The database comes from --db or CANON_CONTEXT_DB and must already be a canon
context store: a missing file, a file that is not SQLite, and a SQLite file
without the store's identity tables are refused before anything writes to
them. A purge that leaves residue, leaves its scrub unfinished or ends with a
failing audit chain exits with a failure code. Previews are scrubbed of
secret-shaped values and have their control characters escaped; JSON output
carries them only with --show-preview.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from .cli_context_text import plan_text, report_text
from .client_mcp_store import SnapshotBusy, table_names
from .cli_format import make_result, write_result
from .cli_parser import describe
from .context_audit import ContextIntegrityError
from .context_migrate import META_TABLE, VERSION_TABLE, ContextStoreIdentityError
from .context_purge import ContextPurgeError, ContextPurgeNotFound, ContextPurgeStale, select
from .context_retention import policy_selection
from .context_store import ContextStore

ENV_CONTEXT_DB = "CANON_CONTEXT_DB"
_POLICY_MAX_BYTES = 1_000_000
_STORE_TABLES = ("records", "audit", META_TABLE, VERSION_TABLE)
_NOT_A_STORE = "the file is not a canon context store"
_FAILURES = ((ContextPurgeStale, "plan_stale"), (ContextPurgeNotFound, "not_found"),
             (ContextPurgeError, "invalid_args"), (ContextIntegrityError, "store_invalid"),
             (ContextStoreIdentityError, "store_invalid"))
_UNFINISHED = {"residue_found": "the purge left residue in the database files",
               "scrub_incomplete": "the file scrub did not finish; run the purge again",
               "audit_failed": "the audit chain does not verify after the purge"}


class _Refusal(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class _Out:
    stdout: TextIO
    stderr: TextIO
    json_output: bool
    color: bool


def add_context_args(parser) -> None:
    subs = parser.add_subparsers(dest="context_command", metavar="context-command",
                                 required=True)
    purge = _child(subs, parser, "purge", "plan or apply a purge of captured context events")
    which = purge.add_mutually_exclusive_group(required=True)
    which.add_argument("--event-id", default=None, help="one captured event record id")
    which.add_argument("--before-ord", type=int, default=None,
                       help="every event captured before this ordinal")
    which.add_argument("--all", action="store_true", dest="all_events",
                       help="every event in the workspace and project")
    purge.add_argument("--keep-responses", action="store_true",
                       help="keep the answers paired with the purged prompts")
    retention = _child(subs, parser, "retention", "apply a retention policy file")
    retention.add_argument("--policy", required=True, help="retention policy JSON file")


def _child(subs, parent, name, help_text):
    child = subs.add_parser(name, help=help_text, description=describe(help_text))
    child._canon_stdout = parent._canon_stdout  # type: ignore[attr-defined]
    child._canon_stderr = parent._canon_stderr  # type: ignore[attr-defined]
    child.add_argument("--db", default=None,
                       help="absolute path of the context database (default: CANON_CONTEXT_DB)")
    child.add_argument("--workspace-id", required=True, help="workspace scope")
    child.add_argument("--project-id", required=True, help="project scope")
    child.add_argument("--show-preview", action="store_true",
                       help="include each event's scrubbed opening words in --json output")
    mode = child.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print the plan and delete nothing")
    mode.add_argument("--confirm-plan", default=None, metavar="SHA256",
                      help="apply only the plan a dry run printed with this digest")
    mode.add_argument("--yes", action="store_true",
                      help="print the plan computed now and apply it without asking")
    return child


def run_context_command(parsed, *, stdin, stdout, stderr, environ, color) -> int:
    out = _Out(stdout, stderr, parsed.json_output, color)
    command = f"context {parsed.context_command}"
    try:
        return _run(parsed, stdin, environ, out, command)
    except _Refusal as exc:
        return _fail(out, command, exc.code, str(exc))
    except tuple(kind for kind, _ in _FAILURES) as exc:
        code = next(code for kind, code in _FAILURES if isinstance(exc, kind))
        return _fail(out, command, code, str(exc))
    except sqlite3.OperationalError as exc:
        busy = "locked" in str(exc) or "busy" in str(exc)
        return _fail(out, command, "store_busy" if busy else "io_error",
                     "the context database is busy; try again" if busy
                     else "the context database could not be used")
    except sqlite3.DatabaseError:
        return _fail(out, command, "store_invalid", _NOT_A_STORE)
    except ValueError as exc:
        return _fail(out, command, "invalid_args", str(exc))


def _run(parsed, stdin, environ, out: _Out, command: str) -> int:
    applies = parsed.yes or parsed.confirm_plan is not None
    if out.json_output and not (parsed.dry_run or applies):
        raise _Refusal("invalid_args", "--json needs --dry-run, --confirm-plan or --yes")
    store = ContextStore(_database(parsed, environ))
    selection = _selection(parsed)
    scope = (parsed.workspace_id, parsed.project_id)
    detail = parsed.show_preview or not out.json_output
    plan = store.purge_plan(*scope, selection, local_detail=detail)
    if parsed.dry_run:
        return _emit(out, command, "dry run: nothing was deleted", plan,
                     plan_text(plan) + "dry run: nothing was deleted\n", plan_only=True)
    digest = parsed.confirm_plan or plan["plan_sha256"]
    if not out.json_output and (parsed.yes or not applies):
        out.stdout.write(plan_text(plan))
    if not applies and plan["entries"]:
        _ask(out, stdin, plan)
    report = store.purge(*scope, selection, confirm_plan_sha256=digest)
    return _emit(out, command, report["status"], report, report_text(report))


def _ask(out: _Out, stdin, plan: dict) -> None:
    out.stdout.write(f"Type purge to delete these {plan['counts']['records']} records: ")
    out.stdout.flush()
    answer = stdin.readline() if stdin is not None else ""
    if answer.strip() != "purge":
        raise _Refusal("not_confirmed", "not confirmed; nothing was deleted")


def _database(parsed, environ) -> Path:
    raw = parsed.db or environ.get(ENV_CONTEXT_DB, "")
    if not raw:
        raise _Refusal("invalid_args", "name the context database with --db or CANON_CONTEXT_DB")
    path = Path(raw)
    if not path.is_absolute():
        raise _Refusal("invalid_args", "the context database path must be absolute")
    if not path.is_file():
        raise _Refusal("not_found", "the context database was not found")
    _require_store(path)
    return path


def _require_store(path: Path) -> None:
    """Read the schema without a byte written to the file or beside it, so a
    file that is not a canon context store is refused untouched."""
    try:
        names = table_names(path.resolve())
    except SnapshotBusy as exc:
        raise _Refusal("store_busy", "the context database is busy; try again") from exc
    except sqlite3.OperationalError:
        raise
    except (sqlite3.DatabaseError, ValueError) as exc:
        raise _Refusal("store_invalid", _NOT_A_STORE) from exc
    if not set(_STORE_TABLES) <= names:
        raise _Refusal("store_invalid", _NOT_A_STORE)


def _selection(parsed):
    if parsed.context_command == "purge":
        return select(event_id=parsed.event_id, before_ord=parsed.before_ord,
                      all_events=parsed.all_events, keep_responses=parsed.keep_responses)
    policy = Path(parsed.policy)
    try:
        if policy.stat().st_size > _POLICY_MAX_BYTES:
            raise _Refusal("invalid_args", "the retention policy file is larger than 1 MB")
        return policy_selection(json.loads(policy.read_text(encoding="utf-8")))
    except OSError as exc:
        raise _Refusal("not_found", "the retention policy file could not be read") from exc
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as exc:
        raise _Refusal("invalid_args", "the retention policy file is not JSON") from exc


def _unfinished(data: dict) -> str | None:
    """The failure code for a report that did not finish cleanly, if any."""
    status = data.get("status")
    if status in _UNFINISHED:
        return status
    return "scrub_incomplete" if data.get("scrub_pending") else None


def _emit(out: _Out, command: str, message: str, data: dict, text: str,
          plan_only: bool = False) -> int:
    """A dry run succeeds whatever the store's scrub mark says: the plan it
    prints names the pending scrub, and a confirmed run finishes it."""
    failure = None if plan_only else _unfinished(data)
    if out.json_output:
        result = make_result(ok=failure is None, command=command,
                             failure_code=failure or "ok",
                             message=_UNFINISHED[failure] if failure else message, data=data)
        return write_result(result, stdout=out.stdout, stderr=out.stderr, json_output=True,
                            color=out.color)
    out.stdout.write(text)
    if failure is None:
        return 0
    return _fail(out, command, failure, _UNFINISHED[failure])


def _fail(out: _Out, command: str, code: str, message: str) -> int:
    result = make_result(ok=False, command=command, failure_code=code, message=message)
    return write_result(result, stdout=out.stdout, stderr=out.stderr,
                        json_output=out.json_output, color=out.color)
