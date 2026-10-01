"""`flywheel monitor ...`: the owner's command line for coverage, review and verify.

Success criteria: coverage lists every path E1 to E14 with PRE, POST or NONE and
never reports an uncovered path as PRE; `approve` refuses without a terminal
(an agent's shell has none) and needs the typed confirmation code; `pending`
lists open holds; `verify` exits 0 on MATCH and 1 on DRIFT.
"""
from __future__ import annotations

import io
import json

from harness.cli_entry import _PACKAGED
from harness.preaction import cli
from harness.preaction.coverage import REGISTRY
from tests.preaction_fixtures import call, ctx, monitor


def _cli(*argv, stdin="", isatty=False):
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(list(argv), stdout=out, stderr=err, stdin=io.StringIO(stdin),
                    isatty=lambda: isatty)
    return code, out.getvalue(), err.getvalue()


def test_monitor_is_a_packaged_command():
    assert _PACKAGED["monitor"] == "harness.preaction.cli"


def test_coverage_lists_every_path_honestly(tmp_path):
    code, out, _ = _cli("coverage", "--home", str(tmp_path), "--json")
    rows = {r["path_id"]: r["state"] for r in json.loads(out)}
    assert code == 0 and set(rows) >= {f"E{i}" for i in range(1, 15)}
    assert rows["E1"] == "PRE" and rows["E10"] == "POST"
    assert rows["E12"] == "NONE" and rows["E7"] == "NONE"
    assert set(REGISTRY) == set(rows)


def test_pending_and_approve_need_a_terminal_and_the_code(tmp_path):
    mon = monitor(tmp_path)
    held = mon.gate(call("run", cmd="git push --force"), ctx())
    code, out, _ = _cli("pending", "--home", str(tmp_path), "--json")
    assert [p["hold_id"] for p in json.loads(out)] == [held.hold_id]
    code, _, err = _cli("approve", held.hold_id, "--home", str(tmp_path))
    assert code == 2 and "terminal" in err
    code, _, _ = _cli("approve", held.hold_id, "--home", str(tmp_path), stdin="nope\n", isatty=True)
    assert code == 1
    pending = mon.escalator.read_pending(held.hold_id)
    code, _, _ = _cli("approve", held.hold_id, "--home", str(tmp_path),
                      stdin=pending["confirm_code"] + "\n", isatty=True)
    assert code == 0
    assert mon.gate(call("run", cmd="git push --force"), ctx()).run


def test_reject_from_cli(tmp_path):
    mon = monitor(tmp_path)
    held = mon.gate(call("run", cmd="git push --force"), ctx())
    pending = mon.escalator.read_pending(held.hold_id)
    code, _, _ = _cli("reject", held.hold_id, "--home", str(tmp_path),
                      stdin=pending["confirm_code"] + "\n", isatty=True)
    assert code == 0 and mon.escalator.pending() == []


def test_verify_exit_codes(tmp_path):
    mon = monitor(tmp_path)
    mon.gate(call("run", cmd="git push --force"), ctx())
    assert _cli("verify", str(tmp_path))[0] == 0
    path = tmp_path / "records.jsonl"
    path.write_text(path.read_text(encoding="utf-8").replace('"HOLD"', '"ALLOW"'), encoding="utf-8")
    assert _cli("verify", str(tmp_path))[0] == 1


def test_install_prints_settings_without_writing(tmp_path):
    code, out, _ = _cli("install", "claude-code", "--home", str(tmp_path), "--print")
    assert code == 0 and "PreToolUse" in json.loads(out)["hooks"]
