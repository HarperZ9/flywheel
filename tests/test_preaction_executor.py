"""P1: the monitor inside ToolExecutor.execute, on by default.

Success criteria (outcome checks, not log lines): a held write leaves the file
unchanged on disk; a held command never spawns; an MCP call is assessed even
though the external branch skips ToolGate.check; existing gate refusals keep
their text and gain a record; the after-receipt carries the preaction block
and stays byte-identical when there is none; the off switch needs a consumed
owner grant; no code calls _execute_inner except the bridge.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from harness.local_tools import ToolExecutor, ToolGate
from harness.preaction.contract import HOLD
from harness.tool_call_receipt import build_receipt, verify_receipt
from tests.preaction_fixtures import Clock, monitor

REPO = Path(__file__).resolve().parents[1]


def _exec(tmp_path, **kw):
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    ex = ToolExecutor(root=str(root), gate=ToolGate(allow_write=True, allow_exec=True, allow_mcp=True), **kw)
    return ex, root


def test_default_monitor_holds_a_planted_write_and_file_is_unchanged(tmp_path):
    ex, root = _exec(tmp_path)
    target = root / ".env"
    target.write_text("KEY=1", encoding="utf-8")
    res = ex.execute("write_file", {"path": ".env", "content": "KEY=stolen"})
    assert not res.ok and res.output.startswith("held for owner review")
    assert target.read_text(encoding="utf-8") == "KEY=1"


def test_held_command_never_spawns(tmp_path):
    ran = []
    ex, root = _exec(tmp_path, runner=lambda cmd, cwd: (ran.append(cmd), (True, "ran"))[1])
    res = ex.execute("run", {"cmd": "git push --force origin main"})
    assert not res.ok and ran == []


def test_benign_calls_still_run(tmp_path):
    ex, root = _exec(tmp_path, runner=lambda cmd, cwd: (True, "[exit 0]\nok"))
    assert ex.execute("write_file", {"path": "a.txt", "content": "hi"}).ok
    assert (root / "a.txt").read_text(encoding="utf-8") == "hi"
    assert ex.execute("run", {"cmd": "python -m pytest -q"}).ok


def test_mcp_call_is_assessed(tmp_path):
    called = []
    ex, _ = _exec(tmp_path, external={"mcp__deploy__release": {
        "fn": lambda a: (called.append(a), (True, "released"))[1], "description": "release"}})
    res = ex.execute("mcp__deploy__release", {"version": "1.2.3"})
    assert not res.ok and called == []


def test_layer0_refusal_text_unchanged_and_recorded(tmp_path):
    root = tmp_path / "r"
    root.mkdir()
    home = tmp_path / "home"
    ex = ToolExecutor(root=str(root), monitor=monitor(home))
    res = ex.execute("write_file", {"path": "a.txt", "content": "x"})
    assert res.output == "[gate] write disabled (pass --allow-write)"
    from harness.preaction.records import HoldStore
    last = HoldStore(home).read_all()[-1]
    assert last["verdict"] == "BLOCK" and last["rule_hits"] == ["layer0/gate"]


def test_receipt_carries_preaction_block_and_escalated_admission(tmp_path):
    rdir = tmp_path / "receipts"
    ex, _ = _exec(tmp_path, receipt_dir=str(rdir))
    ex.init_receipt_chain("run-r")
    ex.execute("run", {"cmd": "git push --force"})
    receipt = json.loads(next(rdir.glob("tool-receipt-*.json")).read_text(encoding="utf-8"))
    assert receipt["admission"] == "ESCALATED" and receipt["outcome"] == "BLOCKED"
    assert receipt["preaction"]["verdict"] == HOLD
    assert list(receipt)[-2:] == ["preaction", "seal"]
    assert verify_receipt(receipt)["verdict"] == "MATCH"


def test_receipt_without_preaction_is_byte_identical():
    kw = dict(tool="read_file", capability="builtin-read", admission="ALLOWED", args={"p": 1},
              output="x", ok=True, rc=0, run_id="r", seq=1)
    assert build_receipt(**kw) == build_receipt(**kw, preaction=None)


def test_allowed_call_receipt_names_allow(tmp_path):
    rdir = tmp_path / "receipts"
    ex, _ = _exec(tmp_path, receipt_dir=str(rdir))
    ex.init_receipt_chain("run-r")
    ex.execute("list_dir", {"path": "."})
    receipt = json.loads(next(rdir.glob("tool-receipt-*.json")).read_text(encoding="utf-8"))
    assert receipt["preaction"]["verdict"] == "ALLOW" and receipt["admission"] == "ALLOWED"


def test_off_switch_without_grant_is_refused(tmp_path):
    from harness.preaction.offswitch import OffSwitchError, monitor_off
    try:
        monitor_off(tmp_path / "home", grant_ref="gnt_" + "0" * 32, run_id="r", clock=Clock())
    except OffSwitchError:
        return
    raise AssertionError("monitor_off accepted a grant that was never issued")


def test_off_switch_with_consumed_owner_grant_runs_unmonitored_and_says_so(tmp_path):
    from harness.preaction.offswitch import issue_off_grant, monitor_off
    clock = Clock()
    home = tmp_path / "home"
    ref = issue_off_grant(home, run_id="r", clock=clock)
    off = monitor_off(home, grant_ref=ref, run_id="r", clock=clock)
    rdir = tmp_path / "receipts"
    ex, _ = _exec(tmp_path, receipt_dir=str(rdir), monitor=off,
                  runner=lambda cmd, cwd: (True, "ran"))
    ex.init_receipt_chain("r")
    assert ex.execute("run", {"cmd": "git push --force"}).ok
    receipt = json.loads(next(rdir.glob("tool-receipt-*.json")).read_text(encoding="utf-8"))
    assert receipt["preaction"]["coverage"] == "UNVERIFIABLE"
    assert receipt["preaction"]["rule_hits"] == ["monitor-off-by-owner-grant"]


def test_single_entry_static_gate_passes_on_the_tree():
    proc = subprocess.run([sys.executable, "scripts/check_preaction_entry.py"], cwd=REPO,
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_single_entry_static_gate_catches_a_planted_caller(tmp_path):
    bad = tmp_path / "harness"
    bad.mkdir()
    (bad / "sneaky.py").write_text("def f(ex):\n    return ex._execute_inner('run', {})\n",
                                   encoding="utf-8")
    proc = subprocess.run([sys.executable, str(REPO / "scripts" / "check_preaction_entry.py"),
                           "--root", str(tmp_path)], capture_output=True, text=True)
    assert proc.returncode == 1 and "sneaky.py" in proc.stdout
