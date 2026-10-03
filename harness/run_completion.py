"""run_completion.py -- what a finished run verified, and what it only claimed.

A run ends with a model saying it is done. That sentence is a claim. This
module sorts each deliverable into one of three verdicts before anyone is told
the run finished:

- verified: a named check ran and passed;
- claimed: the model or its tool said so and nothing checked it;
- failed: a check ran and did not pass, or the run did not complete. A run
  whose step budget ran out before its check ran is failed with the detail
  `not_run`, never as a check that did not pass.

Two deliverables are checked today. Each file the run wrote is re-hashed on
disk at the end of the run and compared with the hash the harness recorded
right after the write (`file_hash_recheck`), so a file that was never written,
was deleted, or was overwritten later fails. The final answer is verified only
by the harness's own test command (`test_command`) or acceptance criteria,
never by the model's word; with neither, it stays claimed.

A file a command changed, rather than a hashed write tool, is listed too. The
end-of-run workspace diff names it in a `workspace_changes` ledger entry, and
it is claimed (`changed_by_command`): nothing recorded what it should hold.

What this does not prove: a file that matches its recorded hash can still be
wrong, and a passing test proves what the test checks and no more. A native
CLI edit reports no hash the harness took, so an Edit stays claimed; only a
full Write, whose content the CLI reports, is rechecked. The last operation on
a path sets what is expected of it.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePath

from .patch_paths import patch_target_paths

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
    # Read the headers the way apply_patch reads them, `+++ path` included.
    return patch_target_paths(args.get("patch") or args.get("diff"))


def path_key(path: str) -> str:
    """One spelling per file, so `./a.py` and `a.py` are not two deliverables."""
    return os.path.normcase(os.path.normpath(str(path).replace(chr(92), "/")))


def workspace_path(path: str, root) -> str | None:
    """A path the run reported, relative to the workspace root.

    A native CLI names files by absolute path. Inside the root it is made
    relative, so the record does not carry the host's layout and a reader can
    use it. Outside the root it is None."""
    if not PurePath(path).is_absolute():
        return path
    try:
        rel = Path(os.path.normpath(path)).relative_to(os.path.normpath(str(root)))
    except ValueError:
        return None
    return rel.as_posix() if rel.parts else None


def command_changes(entries) -> list[str]:
    """Files the end-of-run workspace diff found changed (`workspace_changes`)."""
    paths: list[str] = []
    for entry in entries:
        if _field(entry, "kind") != "workspace_changes":
            continue
        try:
            value = json.loads(_field(entry, "content", "") or "{}")
        except ValueError:
            continue
        listed = value.get("paths") if isinstance(value, dict) else None
        paths += [p for p in listed or () if isinstance(p, str) and p]
    return paths


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


def _command_item(root: Path, path: str) -> dict:
    """A file a command changed: nothing recorded what it should hold."""
    return {"kind": "file", "path": path, "expected_sha256": None, "status": "claimed",
            "check": None, "detail": "changed_by_command",
            "observed_sha256": _observed(root, path)}


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
        if passed is False and tested is None:
            # The step budget ran out before the harness ran its check, so
            # there is no observed failure to report: the check was not run.
            return {**item, "status": "failed", "check": "test_command", "detail": "not_run"}
        detail = ("failed" if passed is not True else "integrity_not_clean" if not trusted
                  else "test_run_not_in_trace")
        return {**item, "status": "failed", "check": "test_command", "detail": detail}
    if result.get("accepted") is not None:
        ok = result.get("accepted_trusted") is True
        return {**item, "status": "verified" if ok else "failed",
                "check": "acceptance_criteria", "detail": "passed" if ok else "failed"}
    return {**item, "status": "claimed", "check": None, "detail": "no_check_ran"}


#: Where a CLI write outside the workspace root is listed. Its host path is
#: not recorded, and nothing here can recheck it, so it stays claimed.
OUTSIDE_WORKSPACE = "(outside the workspace)"


def cli_writes(events, root=None) -> dict[str, str | None]:
    """Files a native CLI session reported writing, with the hash its content implies.

    Calls are read in order and the last one on a path sets what is expected:
    a Write followed by an Edit leaves content no event reported, so the file
    is claimed, not failed against the Write's hash. With `root`, each path is
    made relative to it."""
    calls, failed, writes, outside = {}, set(), {}, 0
    for event in events:
        if event.get("type") == "cli_tool_call":
            calls[event.get("call_id")] = (event.get("tool"), event.get("arguments") or {})
        elif event.get("type") == "cli_tool_result" and event.get("is_error") is True:
            failed.add(event.get("call_id"))
    for ident, (tool, args) in calls.items():
        path = args.get("file_path") if isinstance(args, dict) else None
        if ident in failed or not isinstance(path, str):
            continue
        written = tool == "Write" and isinstance(args.get("content"), str)
        if not written and tool not in CLI_EDIT_TOOLS:
            continue
        rel = path if root is None else workspace_path(path, root)
        if rel is None:
            outside += 1
            writes[f"{OUTSIDE_WORKSPACE} {outside}"] = None
            continue
        writes[rel] = (hashlib.sha256(args["content"].encode("utf-8")).hexdigest()
                       if written else None)
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
    writes = {**ledger_writes(entries), **cli_writes(cli_events, root)}
    items = [_file_item(root, path, expected) for path, expected in writes.items()]
    known = {path_key(path) for path in writes}
    for path in dict.fromkeys(command_changes(entries)):
        if path_key(path) not in known:
            items.append(_command_item(root, path))
    items.sort(key=lambda item: item["path"])
    items.append(_answer_item(result, failure, last_test_run(entries)))
    counts = {status: sum(1 for i in items if i["status"] == status)
              for status in ("verified", "claimed", "failed")}
    monitor = (result or {}).get("behavioral_monitor") or {}
    unbacked = any(flag.get("kind") == "claim_without_receipt"
                   for flag in monitor.get("flags") or ())
    return {"schema": SCHEMA, "verdict": verdict_of(items), "counts": counts,
            "items": items[-MAX_ITEMS:], "items_omitted": max(0, len(items) - MAX_ITEMS),
            "unbacked_success_claim": unbacked, "does_not_prove": list(DOES_NOT_PROVE)}
