"""The content-free verified / claimed / failed split for a terminal projection.

The worker writes a completion report into the private trace (run_completion).
This module projects it without paths or text, and rechecks it against the
trace before it is shown: every file the ledger says was written must appear,
with the hash the ledger recorded, and a final answer marked verified by the
test command must have a passing harness test run in the trace. The same holds
for a native CLI session's Write and Edit calls, read from its progress
records, and for each file the end-of-run workspace diff found changed. A
report that fails a recheck is shown as unverifiable with the reason, so a
completion record cannot claim more than the trace it sits in.
"""
from __future__ import annotations

import re

from .run_completion import (SCHEMA, cli_writes, command_changes, last_test_run,
                             ledger_writes, path_key)

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_STATUSES = ("verified", "claimed", "failed")
_CHECKS = {"file": {None, "file_hash_recheck"},
           "final_answer": {None, "test_command", "acceptance_criteria", "run_state"}}
_REPORT_KEYS = {"schema", "verdict", "counts", "items", "items_omitted",
                "unbacked_success_claim", "does_not_prove"}


class _Unverifiable(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _sha(value) -> bool:
    return type(value) is str and _SHA.fullmatch(value) is not None


_FILE_DETAILS = {"matches", "missing", "changed_after_write", "no_recorded_hash",
                 "changed_by_command"}
_ANSWER_DETAILS = {"passed", "failed", "no_check_ran", "integrity_not_clean",
                   "test_run_not_in_trace", "not_run", "NO_RESULT"}
_REASON = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")


def _plain_detail(kind: str, detail) -> bool:
    """Details are fixed words or a failure code, so the projection stays content-free."""
    if type(detail) is not str:
        return False
    if kind == "file":
        return detail in _FILE_DETAILS
    return detail in _ANSWER_DETAILS or _REASON.fullmatch(detail) is not None


def _check_file(item: dict) -> None:
    expected, observed = item.get("expected_sha256"), item.get("observed_sha256")
    status, check = item["status"], item["check"]
    matched = _sha(expected) and expected == observed
    if (type(item.get("path")) is not str
            or status == "verified" and not (check == "file_hash_recheck" and matched)
            or status == "failed" and (check != "file_hash_recheck" or matched
                                       or not _sha(expected))
            or status == "claimed" and (check is not None or expected is not None)):
        raise _Unverifiable("COMPLETION_ITEM_NOT_SUPPORTED")


def _check_items(items: list, terminal_state: str, tested) -> None:
    answers = [i for i in items if type(i) is dict and i.get("kind") == "final_answer"]
    if len(answers) != 1 or items[-1] is not answers[0]:
        raise _Unverifiable("COMPLETION_RECORD_MALFORMED")
    for item in items:
        if (type(item) is not dict or item.get("kind") not in _CHECKS
                or item.get("status") not in _STATUSES
                or item.get("check") not in _CHECKS[item["kind"]]
                or not _plain_detail(item["kind"], item.get("detail"))):
            raise _Unverifiable("COMPLETION_RECORD_MALFORMED")
        if item["kind"] == "file":
            _check_file(item)
    answer = answers[0]
    if answer["status"] == "verified" and terminal_state == "failed":
        raise _Unverifiable("COMPLETION_VERIFIED_ON_FAILED_RUN")
    if answer["check"] == "test_command" and answer["status"] == "verified" \
            and tested is not True:
        raise _Unverifiable("COMPLETION_TEST_NOT_IN_TRACE")
    if answer["status"] == "claimed" and answer["check"] is not None:
        raise _Unverifiable("COMPLETION_ITEM_NOT_SUPPORTED")
    if answer["detail"] == "not_run" and (
            answer["check"] != "test_command" or answer["status"] != "failed"
            or tested is not None):
        # "Not run" is true only when the trace holds no harness check run.
        raise _Unverifiable("COMPLETION_ITEM_NOT_SUPPORTED")


def _check_coverage(items: list, writes: dict, changed=()) -> None:
    files = {i["path"]: i.get("expected_sha256") for i in items if i["kind"] == "file"}
    for path, recorded in writes.items():
        if path not in files:
            raise _Unverifiable("COMPLETION_OMITS_WRITE")
        if files[path] != recorded:
            raise _Unverifiable("COMPLETION_HASH_NOT_FROM_TRACE")
    listed = {path_key(path) for path in files}
    if any(path_key(path) not in listed for path in changed):
        raise _Unverifiable("COMPLETION_OMITS_WRITE")


def _writes(ledger: list, cli_events: list, root) -> dict:
    """Every write the trace records: ledger write tools, then CLI calls."""
    return {**ledger_writes(ledger), **cli_writes(cli_events, root)}


def _verdict(counts: dict) -> str:
    if counts["failed"]:
        return "failed"
    return "claimed" if counts["claimed"] else "verified"


def _check_report(report, ledger: list, terminal_state: str, cli_events=(),
                  root=None) -> dict:
    if type(report) is not dict or report.get("schema") != SCHEMA:
        raise _Unverifiable("COMPLETION_RECORD_MALFORMED")
    if report.get("verdict") == "unavailable":
        raise _Unverifiable("COMPLETION_CHECK_FAILED")
    counts, items, omitted = report.get("counts"), report.get("items"), report.get("items_omitted")
    if (set(report) != _REPORT_KEYS or type(items) is not list or not items
            or type(omitted) is not int or omitted < 0
            or type(counts) is not dict or set(counts) != set(_STATUSES)
            or any(type(v) is not int or v < 0 for v in counts.values())
            or type(report["unbacked_success_claim"]) is not bool):
        raise _Unverifiable("COMPLETION_RECORD_MALFORMED")
    _check_items(items, terminal_state, last_test_run(ledger))
    visible = {s: sum(1 for i in items if i["status"] == s) for s in _STATUSES}
    if (omitted == 0 and visible != counts or sum(counts.values()) != len(items) + omitted
            or report["verdict"] != _verdict(counts)):
        raise _Unverifiable("COMPLETION_VERDICT_MISMATCH")
    if omitted == 0:
        _check_coverage(items, _writes(ledger, list(cli_events), root),
                        command_changes(ledger))
    return {"status": "recorded", "verdict": report["verdict"], "counts": dict(counts),
            "items": [{k: i[k] for k in ("kind", "status", "check", "detail")} for i in items],
            "items_omitted": omitted,
            "unbacked_success_claim": report["unbacked_success_claim"]}


def trace_workspace_root(records: list):
    """The pinned workspace root the run's binding names, for CLI paths."""
    for record in records:
        if record.get("kind") == "request":
            binding = record["payload"].get("execution_binding") or {}
            root = (binding.get("workspace") or {}).get("root")
            return root if type(root) is str else None
    return None


def derive_completion(records: list, terminal_state: str) -> dict:
    """Project the recorded completion report, or say why it cannot be shown."""
    terminal = next((r for r in reversed(records) if r.get("kind") in {"result", "failure"}),
                    None)
    report = None if terminal is None else terminal["payload"].get("completion")
    if report is None:
        return {"status": "unrecorded"}
    ledger = [r["payload"] for r in records if r.get("kind") == "ledger"]
    cli_events = [r["payload"] for r in records if r.get("kind") == "progress"
                  and str(r["payload"].get("type", "")).startswith("cli_tool")]
    try:
        block = _check_report(report, ledger, terminal_state, cli_events,
                              trace_workspace_root(records))
    except _Unverifiable as exc:
        return {"status": "unverifiable", "reason": exc.reason}
    except (KeyError, TypeError, ValueError, AttributeError):
        return {"status": "unverifiable", "reason": "COMPLETION_DERIVATION_FAILED"}
    return block
