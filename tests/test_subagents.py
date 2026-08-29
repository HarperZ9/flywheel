"""The subagent swarm engine: role-prompted fan-out with per-child
receipts, deterministic quorum fan-in, and the agent.completed hook
fired from the run root's registry. Roles cannot hold authority outside
their grant set; children run argv in their own workspaces."""
import json
import time
from pathlib import Path

import pytest

from harness import subagents
from harness.subagents import (
    SwarmRunner,
    quorum,
    validate_child,
)


class _FakeHandle:
    def __init__(self, *, exit_code=0, output="", hang=False):
        self.exit_code = exit_code
        self.output = output
        self.hang = hang
        self.stopped = False

    @property
    def pid(self):
        return None

    def wait(self, timeout_s):
        if self.hang:
            raise TimeoutError
        return self.exit_code, self.output

    def stop(self):
        self.stopped = True
        return True


class _BlockingHandle:
    """A child that runs until stopped, like a real worker process."""

    def __init__(self):
        import threading
        self.stopped = False
        self._done = threading.Event()

    @property
    def pid(self):
        return None

    def wait(self, timeout_s):
        self._done.wait(timeout=min(float(timeout_s), 5.0))
        return (1, "") if self.stopped else (0, "")

    def stop(self):
        self.stopped = True
        self._done.set()
        return True


def _write_result(workspace, spec, status="completed", **extra):
    payload = {"schema": subagents.RESULT_SCHEMA,
               "spec_sha256": spec["spec_sha256"],
               "role": spec["role"], "status": status}
    payload.update(extra)
    (Path(workspace) / "result.json").write_text(
        json.dumps(payload), encoding="utf-8")


def _ok_factory(spec_path, workspace):
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    _write_result(workspace, spec)
    return _FakeHandle()


def _spawn(runner, children=None, **kw):
    kw.setdefault("goal", "map the auth module")
    kw.setdefault("endpoint", "dry")
    if children is None:
        children = [{"role": "explore"}, {"role": "verify"}]
    return runner.spawn(children=children, **kw)


def _await_sealed(runner, swarm_id):
    for _ in range(500):
        snap = runner.snapshot(swarm_id)
        if snap and snap["status"] == "sealed":
            return snap
        time.sleep(0.01)
    raise AssertionError("the swarm never sealed")


def test_spawn_fans_out_children_and_seals_per_child_receipts(tmp_path):
    runner = SwarmRunner(run_root=tmp_path)
    ack = _spawn(runner, handle_factory=_ok_factory)
    assert ack["status"] == "running"
    assert [c["role"] for c in ack["children"]] == ["explore", "verify"]
    snap = _await_sealed(runner, ack["swarm_id"])
    receipt = snap["receipt"]
    assert receipt["schema"] == "flywheel.subagent-swarm/v1"
    assert receipt["verdict"] == "satisfied"
    assert receipt["completed"] == 2 and receipt["total"] == 2
    for child in receipt["children"]:
        assert child["schema"] == "flywheel.subagent-run/v1"
        assert child["status"] == "completed" and child["result_ok"]
        assert len(child["spec_sha256"]) == 64
        assert child["output_sha256"] == ""
    # every child got its own scratch workspace under the swarm dir
    for c in ack["children"]:
        ws = tmp_path / "subagents" / ack["swarm_id"] / ("work_" + c["child_id"])
        assert ws.is_dir()
    # the sealed receipt persists at the swarm dir
    persisted = json.loads((tmp_path / "subagents" / ack["swarm_id"]
                            / "swarm.json").read_text(encoding="utf-8"))
    assert persisted["swarm_id"] == receipt["swarm_id"]


def test_role_policy_refuses_unknown_roles_and_escalation():
    assert validate_child("explore")["allow_write"] is False
    with pytest.raises(ValueError):
        validate_child("mastermind")
    with pytest.raises(ValueError):
        validate_child("explore", allow_write=True)
    with pytest.raises(ValueError):
        validate_child("plan", allow_exec=True)
    with pytest.raises(ValueError):
        validate_child("explore", prompt="x" * 3000)
    assert validate_child("implement", allow_write=True)["allow_write"]


def test_timeout_child_is_stopped_and_marks_the_swarm_unsatisfied(tmp_path):
    seen = []

    def factory(spec_path, workspace):
        handle = _FakeHandle(hang=True)
        seen.append(handle)
        return handle

    runner = SwarmRunner(run_root=tmp_path)
    ack = _spawn(runner, [{"role": "verify"}],
                 timeout_s=5.0, handle_factory=factory)
    snap = _await_sealed(runner, ack["swarm_id"])
    assert seen[0].stopped, "an overrunning child must be stopped"
    child = snap["receipt"]["children"][0]
    assert child["status"] == "timeout" and child["timed_out"]
    assert child["exit_code"] == -1
    assert snap["receipt"]["verdict"] == "unsatisfied"


def test_quorum_policies_are_deterministic():
    assert quorum("all", 1, 2) == {"required": 2, "completed": 1,
                                   "total": 2, "verdict": "unsatisfied"}
    assert quorum("any", 1, 2)["verdict"] == "satisfied"
    assert quorum("majority", 1, 2)["verdict"] == "unsatisfied"
    assert quorum("majority", 2, 3)["verdict"] == "satisfied"
    with pytest.raises(ValueError):
        quorum("most", 1, 2)


def test_failed_and_tampered_children_are_not_completed(tmp_path):
    def factory(spec_path, workspace):
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
        if spec["role"] == "verify":
            _write_result(workspace, spec)          # honest result, crash exit
            return _FakeHandle(exit_code=3)
        _write_result(workspace, spec, spec_sha256="0" * 64)  # tampered seal
        return _FakeHandle()

    runner = SwarmRunner(run_root=tmp_path)
    ack = _spawn(runner, handle_factory=factory)
    snap = _await_sealed(runner, ack["swarm_id"])
    statuses = {c["role"]: c["status"] for c in snap["receipt"]["children"]}
    assert statuses == {"verify": "failed", "explore": "failed"}
    assert snap["receipt"]["completed"] == 0


def _verdict_factory(accepted):
    def factory(spec_path, workspace):
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
        _write_result(workspace, spec, verdict={
            "schema": "flywheel.run-verdict/v1", "accepted": accepted,
            "chain_intact": True, "integrity_clean": accepted,
            "tests_pass_trusted": accepted, "chain_head": "head_" + spec["role"],
            "integrity_sha256": "abc123"})
        return _FakeHandle()
    return factory


def test_verified_quorum_counts_accepted_verdicts_and_seals_a_swarm_cert(tmp_path):
    runner = SwarmRunner(run_root=tmp_path)
    ack = _spawn(runner, handle_factory=_verdict_factory(True))
    r = _await_sealed(runner, ack["swarm_id"])["receipt"]
    assert r["completed"] == 2
    assert r["verified"]["accepted"] == 2 and r["verified"]["verdict"] == "satisfied"
    assert r["swarm_cert"]["accepted"] == 2 and len(r["swarm_cert"]["cert_sha256"]) == 16
    assert all(c["accepted"] and c["chain_head"] for c in r["swarm_cert"]["children"])


def test_a_completed_but_unaccepted_child_fails_the_verified_quorum(tmp_path):
    # both children exit 0 (completed), but their witnessed verdict is NOT accepted
    # (a tampered grader): the completed quorum is satisfied, the verified one is not.
    runner = SwarmRunner(run_root=tmp_path)
    ack = _spawn(runner, handle_factory=_verdict_factory(False))
    r = _await_sealed(runner, ack["swarm_id"])["receipt"]
    assert r["completed"] == 2 and r["verdict"] == "satisfied"        # ran and reported
    assert r["verified"]["accepted"] == 0 and r["verified"]["verdict"] == "unsatisfied"
    assert not any(c["accepted"] for c in r["swarm_cert"]["children"])


def test_a_verdictless_child_completes_but_is_never_verified(tmp_path):
    # a child that reports with no witnessed verdict counts as completed, never accepted
    runner = SwarmRunner(run_root=tmp_path)
    ack = _spawn(runner, handle_factory=_ok_factory)
    r = _await_sealed(runner, ack["swarm_id"])["receipt"]
    assert r["completed"] == 2 and r["verified"]["accepted"] == 0
    assert r["verified"]["verdict"] == "unsatisfied"


def test_fanin_fires_agent_completed_hooks_with_teeth(tmp_path):
    from harness.accountable_hooks import register_hook, save_registry

    reg = register_hook(event="agent.completed",
                        argv=["python", "-c", "import sys; sys.exit(9)"],
                        blocking=True, hook_id="hook_" + "d" * 8,
                        created_at="2026-08-24T12:00:00Z")
    save_registry([reg], registry_path=tmp_path / "hooks" / "registry.json")
    runner = SwarmRunner(run_root=tmp_path)
    ack = _spawn(runner, handle_factory=_ok_factory)
    snap = _await_sealed(runner, ack["swarm_id"])
    assert snap["receipt"]["event_blocked"] is True
    hook_receipt = snap["receipt"]["hook_receipts"][0]
    assert hook_receipt["event"] == "agent.completed"
    assert hook_receipt["exit_code"] == 9 and hook_receipt["blocked"]


def test_sealed_summaries_lists_persisted_swarms(tmp_path):
    runner = SwarmRunner(run_root=tmp_path)
    first = _spawn(runner, handle_factory=_ok_factory)
    _await_sealed(runner, first["swarm_id"])
    second = _spawn(runner, handle_factory=_ok_factory)
    _await_sealed(runner, second["swarm_id"])
    rows = {r["swarm_id"]: r for r in subagents.sealed_summaries(tmp_path)}
    assert set(rows) == {first["swarm_id"], second["swarm_id"]}
    assert all(r["verdict"] == "satisfied" and r["total"] == 2
               for r in rows.values())
    assert runner.snapshot(first["swarm_id"])["status"] == "sealed"


def test_spawn_refuses_bad_bounds(tmp_path):
    runner = SwarmRunner(run_root=tmp_path)
    with pytest.raises(ValueError):
        _spawn(runner, goal="")
    with pytest.raises(ValueError):
        _spawn(runner, endpoint="")
    with pytest.raises(ValueError):
        _spawn(runner, quorum_policy="most")
    with pytest.raises(ValueError):
        _spawn(runner, timeout_s=1.0)
    with pytest.raises(ValueError):
        _spawn(runner, children=[])
    with pytest.raises(ValueError):
        _spawn(runner, max_steps=99)
