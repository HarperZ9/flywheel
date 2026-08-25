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
    child_status,
    compose_goal,
    quorum,
    read_child_result,
    validate_child,
)


class _FakeHandle:
    def __init__(self, *, exit_code=0, output="", hang=False):
        self.exit_code = exit_code
        self.output = output
        self.hang = hang
        self.stopped = False

    def wait(self, timeout_s):
        if self.hang:
            raise TimeoutError
        return self.exit_code, self.output

    def stop(self):
        self.stopped = True
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


def test_worker_completes_against_the_real_loop_contract(tmp_path,
                                                         monkeypatch):
    import harness.subagent_worker as worker

    captured = {}

    def fake_agent(goal, endpoint, **kw):
        captured.update(goal=goal, endpoint=endpoint, **kw)
        return {"final": "mapped: auth lives in src/auth.py",
                "steps": 2, "tests_pass_trusted": True}

    monkeypatch.setattr(worker, "run_router_agent", fake_agent)
    runner = SwarmRunner(run_root=tmp_path)
    ack = _spawn(runner, [{"role": "explore"}], handle_factory=_ok_factory)
    _await_sealed(runner, ack["swarm_id"])
    # the production worker path: same validation the parent issued
    spec_dir = tmp_path / "subagents" / ack["swarm_id"]
    spec = json.loads(next(spec_dir.glob("*.spec.json")).read_text(
        encoding="utf-8"))
    code = worker.main([str(spec_dir / (spec["child_id"] + ".spec.json"))])
    assert code == 0
    result = read_child_result(Path(spec["workspace"]))
    assert result["status"] == "completed"
    assert result["tests_pass_trusted"] is True
    assert captured["allow_write"] is False
    assert captured["goal"].startswith(subagents.BUILTIN_PROMPTS["explore"])


def test_worker_reports_agent_failure_and_refuses_tampered_specs(
        tmp_path, monkeypatch):
    import harness.subagent_worker as worker

    def boom(*a, **k):
        raise RuntimeError("endpoint down")

    monkeypatch.setattr(worker, "run_router_agent", boom)
    good = {"schema": subagents.SPEC_SCHEMA, "swarm_id": "swarm_" + "a" * 12,
            "child_id": "sa_" + "b" * 8, "role": "explore", "prompt": "",
            "goal": "g", "endpoint": "dry", "model": "", "max_steps": 6,
            "allow_write": False, "allow_exec": False,
            "workspace": str(tmp_path / "ws"), "created_at": "t"}
    good["spec_sha256"] = subagents.canonical_sha256(good)
    assert worker.execute(validated := subagents.validate_spec(dict(good))) == 2
    result = read_child_result(tmp_path / "ws")
    assert result["status"] == "failed" and result["error"] == "RuntimeError"

    tampered = dict(good, goal="evil")
    (tmp_path / "tampered.json").write_text(json.dumps(tampered),
                                            encoding="utf-8")
    assert worker.main([str(tmp_path / "tampered.json")]) == worker.EXIT_BAD_SPEC
    assert compose_goal("", "g") == "g"
    assert child_status(0, True) == "completed"
    assert child_status(0, False) == "failed"
