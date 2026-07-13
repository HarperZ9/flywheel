"""test_held_out_gate.py — the held-out oracle tier: accept needs the visible
suite AND a hidden check the model never saw, and not a reward-hacked pass.

Success criteria:
  - accept_gate composes visible + held-out under rule="all", wrapped by the guard.
  - PytestOracle(cmd_attr=...) runs the held-out command; load_task reads it.
  - end to end: a solution that passes the visible test but fails the hidden one
    is REJECTED; one that passes both is accepted.
"""
import json

from harness.consensus import ConsensusOracle, accept_gate
from harness.integrity import GuardedOracle
from harness.oracle import PytestOracle
from harness.task import Task, load_task


def _task(held_out=""):
    return Task(task_id="t", prompt="p", oracle="pytest",
                oracle_cmd="python -m pytest test_visible.py", workdir=".",
                candidate_path="sol.py", held_out_cmd=held_out)


def test_accept_gate_composes_visible_and_held_out():
    g = accept_gate(_task(held_out="python -m pytest test_hidden.py"))
    assert isinstance(g, GuardedOracle)
    assert isinstance(g.base, ConsensusOracle) and len(g.base.members) == 2
    assert g.base.rule == "all"


def test_accept_gate_is_just_visible_when_no_held_out():
    g = accept_gate(_task())
    assert isinstance(g, GuardedOracle)
    assert g.oracle_type == "guarded:pytest"


def test_accept_gate_can_skip_the_guard():
    g = accept_gate(_task(held_out="python -m pytest test_hidden.py"), guard=False)
    assert isinstance(g, ConsensusOracle)


def test_pytest_oracle_cmd_attr_selects_the_held_out_command():
    t = _task(held_out="python -m pytest test_hidden.py")
    assert "test_hidden.py" in PytestOracle(cmd_attr="held_out_cmd")._cmd(t)
    assert "test_visible.py" in PytestOracle()._cmd(t)


def test_load_task_reads_held_out_cmd(tmp_path):
    (tmp_path / "task.json").write_text(json.dumps({
        "task_id": "t", "prompt": "p", "oracle": "pytest",
        "oracle_cmd": "python -m pytest test_visible.py",
        "held_out_cmd": "python -m pytest test_hidden.py",
        "candidate_path": "sol.py"}), encoding="utf-8")
    task = load_task(tmp_path, workdir=tmp_path / "wd")
    assert task.held_out_cmd == "python -m pytest test_hidden.py"


def _held_out_task(tmp_path, hidden_assert):
    (tmp_path / "test_visible.py").write_text(
        "from sol import f\ndef test_v():\n    assert f() == 1\n", encoding="utf-8")
    (tmp_path / "test_hidden.py").write_text(
        f"from sol import f\ndef test_h():\n    assert {hidden_assert}\n", encoding="utf-8")
    return Task(task_id="t", prompt="p", oracle="pytest",
                oracle_cmd="python -m pytest test_visible.py",
                held_out_cmd="python -m pytest test_hidden.py",
                workdir=str(tmp_path), candidate_path="sol.py")


def test_held_out_tier_rejects_pass_that_fails_the_hidden_check(tmp_path):
    task = _held_out_task(tmp_path, hidden_assert="f() == 2")     # candidate returns 1
    res = accept_gate(task, timeout=60).verify("def f():\n    return 1\n", task)
    assert res.passed is False                                    # visible passed, held-out failed


def test_held_out_tier_accepts_when_both_pass(tmp_path):
    task = _held_out_task(tmp_path, hidden_assert="f() > 0")      # both hold for return 1
    res = accept_gate(task, timeout=60).verify("def f():\n    return 1\n", task)
    assert res.passed is True
