"""The subagent worker path: spec validation, loop execution, result
writing, and tamper refusal for an individual child."""
import json
import time
from pathlib import Path

from harness import subagents
from harness.subagents import (
    SwarmRunner,
    child_status,
    compose_goal,
    read_child_result,
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
