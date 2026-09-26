"""A native CLI session's writes are sorted in order and rechecked by the gateway.

The CLI reports absolute paths and never a hash. The last operation on a path
sets what is expected of it, paths are made relative to the workspace, and
the gateway reads the same progress records the worker did, so a report that
leaves out a CLI write, or a file a command changed, is unverifiable.
"""
import copy
import hashlib
import json

from harness.gateway_completion_outcome import derive_completion
from harness.run_completion import OUTSIDE_WORKSPACE, cli_writes, completion_report


def _call(ident, tool, **args):
    return {"type": "cli_tool_call", "call_id": ident, "tool": tool, "arguments": args}


def test_a_write_then_an_edit_leaves_the_file_claimed_not_failed(tmp_path):
    (tmp_path / "a.py").write_bytes(b"x = 2\n")
    events = [_call("w", "Write", file_path="a.py", content="x = 1\n"),
              _call("e", "Edit", file_path="a.py", old_string="1", new_string="2")]
    report = completion_report([], {"final": "done"}, tmp_path, cli_events=events)
    assert [(i.get("path"), i["status"], i["detail"]) for i in report["items"]] == [
        ("a.py", "claimed", "no_recorded_hash"), (None, "claimed", "no_check_ran")]
    assert report["verdict"] == "claimed"


def test_an_edit_then_a_write_is_rechecked_against_the_write(tmp_path):
    (tmp_path / "a.py").write_bytes(b"x = 3\n")
    events = [_call("e", "Edit", file_path="a.py", old_string="1", new_string="2"),
              _call("w", "Write", file_path="a.py", content="x = 3\n")]
    report = completion_report([], {"final": "done"}, tmp_path, cli_events=events)
    assert report["items"][0]["status"] == "verified"


def test_absolute_cli_paths_are_made_relative_to_the_workspace(tmp_path):
    root = tmp_path / "ws"
    (root / "src").mkdir(parents=True)
    (root / "src" / "db.py").write_text("ok", encoding="utf-8")
    events = [_call("w", "Write", file_path=str(root / "src" / "db.py"), content="ok"),
              _call("o", "Write", file_path=str(tmp_path / "elsewhere.txt"), content="x")]
    writes = cli_writes(events, root)
    assert writes == {"src/db.py": hashlib.sha256(b"ok").hexdigest(),
                      f"{OUTSIDE_WORKSPACE} 1": None}
    report = completion_report([], {"final": "done"}, root, cli_events=events)
    assert str(tmp_path) not in json.dumps(report)
    assert report["items"][0]["status"] == "claimed"
    assert report["items"][1] == {**report["items"][1], "path": "src/db.py",
                                  "status": "verified"}


def _records(root, events, report, ledger=()):
    rows = [{"kind": "request", "payload": {"execution_binding": {
        "workspace": {"root": str(root)}}}}]
    rows += [{"kind": "ledger", "payload": entry} for entry in ledger]
    rows += [{"kind": "progress", "payload": event} for event in events]
    rows.append({"kind": "result", "payload": {"final": "ok", "completion": report}})
    return rows


def _drop_first_file(report):
    dropped = copy.deepcopy(report)
    gone = dropped["items"].pop(0)
    dropped["counts"][gone["status"]] -= 1
    statuses = {i["status"] for i in dropped["items"]}
    dropped["verdict"] = ("failed" if "failed" in statuses
                          else "verified" if statuses == {"verified"} else "claimed")
    return dropped


def test_the_gateway_rechecks_cli_writes_against_the_trace(tmp_path):
    (tmp_path / "x.txt").write_text("hi", encoding="utf-8")
    events = [_call("t1", "Write", file_path=str(tmp_path / "x.txt"), content="hi"),
              {"type": "cli_tool_result", "call_id": "t1", "is_error": False}]
    report = completion_report([], {"final": "ok"}, tmp_path, cli_events=events)
    assert derive_completion(_records(tmp_path, events, report), "completed")["status"] \
        == "recorded"
    omitted = derive_completion(_records(tmp_path, events, _drop_first_file(report)),
                                "completed")
    assert omitted == {"status": "unverifiable", "reason": "COMPLETION_OMITS_WRITE"}
    forged = copy.deepcopy(report)
    forged["items"][0]["expected_sha256"] = forged["items"][0]["observed_sha256"] = "0" * 64
    assert derive_completion(_records(tmp_path, events, forged), "completed")["reason"] \
        == "COMPLETION_HASH_NOT_FROM_TRACE"


def test_the_gateway_requires_each_file_a_command_changed(tmp_path):
    ledger = [{"kind": "workspace_changes", "content": json.dumps(
        {"paths": ["out/report.csv"], "count": 1}), "meta": {}}]
    report = completion_report(ledger, {"final": "ok"}, tmp_path)
    assert [(i.get("path"), i["detail"]) for i in report["items"]] == [
        ("out/report.csv", "changed_by_command"), (None, "no_check_ran")]
    records = _records(tmp_path, [], report, ledger)
    assert derive_completion(records, "completed")["verdict"] == "claimed"
    assert derive_completion(_records(tmp_path, [], _drop_first_file(report), ledger),
                             "completed")["reason"] == "COMPLETION_OMITS_WRITE"
