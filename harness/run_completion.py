"""run_completion.py -- what a finished run verified, and what it only claimed.

A run ends with a model saying it is done. That sentence is a claim. This
module sorts each deliverable into one of three verdicts before anyone is told
the run finished:

- verified: a named check ran and passed;
- claimed: the model or its tool said so and nothing checked it;
- failed: a check ran and did not pass, or the run did not complete.

Two deliverables are checked today. Each file the run wrote is re-hashed on
disk at the end of the run and compared with the hash the harness recorded
right after the write (`file_hash_recheck`), so a file that was never written,
was deleted, or was overwritten later fails. The final answer is verified only
by the harness's own test command (`test_command`) or acceptance criteria,
never by the model's word; with neither, it stays claimed.

What this does not prove: a file that matches its recorded hash can still be
wrong, and a passing test proves what the test checks and no more. A native
CLI edit reports no hash the harness took, so an Edit stays claimed; only a
full Write, whose content the CLI reports, is rechecked.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

SCHEMA = "flywheel.run-completion/v1"
WRITE_TOOLS = frozenset({"write_file", "edit_file", "apply_patch"})
CLI_EDIT_TOOLS = frozenset({"Edit", "MultiEdit", "NotebookEdit", "file_change"})
MAX_ITEMS = 64
DOES_NOT_PROVE = ["NOT_SEMANTIC_CORRECTNESS", "HASH_RECHECK_IS_NOT_A_TEST",
                  "TEST_PASS_PROVES_ONLY_WHAT_THE_TEST_CHECKS"]


def _field(entry, name, default=None):
    return entry.get(name, default) if isinstance(entry, dict) else getattr(entry, name, default)


def _parse_call(content: str) -> tuple[str, dict]:
    name, _, rest = (content or "").partition(" ")
    try:
        args = json.loads(rest) if rest else {}
    except ValueError:
        args = {}
    return name, args if isinstance(args, dict) else {}


def _claimed_paths(name: str, args: dict) -> list[str]:
    if name in ("write_file", "edit_file") and args.get("path"):
        return [str(args["path"])]
    patch = str(args.get("patch") or args.get("diff") or "")
    return [ln[6:].strip() for ln in patch.splitlines() if ln.startswith("+++ b/")]


def ledger_writes(entries) -> dict[str, str | None]:
    """Each path a write tool reported success on, with the last hash recorded.

    None means the tool reported success but the harness took no hash, so the
    write can only be claimed."""
    writes: dict[str, str | None] = {}
    call = ("", {})
    for entry in entries:
        kind, meta = _field(entry, "kind"), _field(entry, "meta") or {}
        if kind == "tool_call":
            call = _parse_call(_field(entry, "content", ""))
        elif (kind == "tool_result" and meta.get("tool") in WRITE_TOOLS
              and meta.get("ok") is True):
            edited = meta.get("edited") if isinstance(meta.get("edited"), dict) else {}
            for path in _claimed_paths(*call) if call[0] == meta.get("tool") else []:
                writes.setdefault(path, None)
            writes.update({str(p): str(h) for p, h in edited.items()})
    return writes


def last_test_run(entries) -> bool | None:
    """The outcome of the harness's own last test-gate run, or None if none ran."""
    outcome = None
    for entry in entries:
        meta = _field(entry, "meta") or {}
        if (_field(entry, "kind") == "tool_result" and meta.get("gate") == "test"
                and meta.get("tool") == "run"):
            outcome = meta.get("ok") is True
    return outcome


def _observed(root: Path, path: str) -> str | None:
    target = (root / path).resolve()
    if not target.is_relative_to(root.resolve()) or not target.is_file():
        return None
    try:
        return hashlib.sha256(target.read_bytes()).hexdigest()
    except OSError:
        return None


def _file_item(root: Path, path: str, expected: str | None) -> dict:
    item = {"kind": "file", "path": path, "expected_sha256": expected}
    if expected is None:
        return {**item, "status": "claimed", "check": None, "detail": "no_recorded_hash",
                "observed_sha256": None}
    observed = _observed(root, path)
    detail = ("matches" if observed == expected
              else "missing" if observed is None else "changed_after_write")
    return {**item, "status": "verified" if detail == "matches" else "failed",
            "check": "file_hash_recheck", "detail": detail, "observed_sha256": observed}


def _answer_item(result: dict | None, failure: str | None, tested: bool | None) -> dict:
    item = {"kind": "final_answer"}
    if failure is not None or result is None:
        return {**item, "status": "failed", "check": "run_state",
                "detail": failure or "NO_RESULT"}
    passed = result.get("tests_pass")
    if passed is not None:
        trusted = result.get("tests_pass_trusted") is True
        if passed is True and trusted and tested is True:
            return {**item, "status": "verified", "check": "test_command", "detail": "passed"}
        detail = ("failed" if passed is not True else "integrity_not_clean" if not trusted
                  else "test_run_not_in_trace")
        return {**item, "status": "failed", "check": "test_command", "detail": detail}
    if result.get("accepted") is not None:
        ok = result.get("accepted_trusted") is True
        return {**item, "status": "verified" if ok else "failed",
                "check": "acceptance_criteria", "detail": "passed" if ok else "failed"}
    return {**item, "status": "claimed", "check": None, "detail": "no_check_ran"}


def cli_writes(events) -> dict[str, str | None]:
    """Files a native CLI session reported writing, with the hash its content implies."""
    calls, failed, writes = {}, set(), {}
    for event in events:
        if event.get("type") == "cli_tool_call":
            calls[event.get("call_id")] = (event.get("tool"), event.get("arguments") or {})
        elif event.get("type") == "cli_tool_result" and event.get("is_error") is True:
            failed.add(event.get("call_id"))
    for ident, (tool, args) in calls.items():
        path = args.get("file_path") if isinstance(args, dict) else None
        if ident in failed or not isinstance(path, str):
            continue
        if tool == "Write" and isinstance(args.get("content"), str):
            writes[path] = hashlib.sha256(args["content"].encode("utf-8")).hexdigest()
        elif tool in CLI_EDIT_TOOLS:
            writes.setdefault(path, None)
    return writes


def verdict_of(items: list[dict]) -> str:
    statuses = {item["status"] for item in items}
    if "failed" in statuses:
        return "failed"
    return "verified" if statuses == {"verified"} else "claimed"


def completion_report(entries, result: dict | None, root, *, failure: str | None = None,
                      cli_events=()) -> dict:
    """Sort a run's deliverables into verified, claimed and failed."""
    root = Path(root)
    writes = {**ledger_writes(entries), **cli_writes(cli_events)}
    items = [_file_item(root, path, expected) for path, expected in sorted(writes.items())]
    items.append(_answer_item(result, failure, last_test_run(entries)))
    counts = {status: sum(1 for i in items if i["status"] == status)
              for status in ("verified", "claimed", "failed")}
    monitor = (result or {}).get("behavioral_monitor") or {}
    unbacked = any(flag.get("kind") == "claim_without_receipt"
                   for flag in monitor.get("flags") or ())
    return {"schema": SCHEMA, "verdict": verdict_of(items), "counts": counts,
            "items": items[-MAX_ITEMS:], "items_omitted": max(0, len(items) - MAX_ITEMS),
            "unbacked_success_claim": unbacked, "does_not_prove": list(DOES_NOT_PROVE)}
