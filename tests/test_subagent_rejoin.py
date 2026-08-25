"""Cross-restart swarm control: live-state persistence, adoption of
detached swarms after a restart, and cancellation that seals what
actually finished. Cancelled children are never silently successful."""
import json
import time
from pathlib import Path

from harness import subagents
from harness.subagents import SwarmRunner


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


def _spawn(runner, children=None, **kw):
    kw.setdefault("goal", "map the auth module")
    kw.setdefault("endpoint", "dry")
    if children is None:
        children = [{"role": "explore"}]
    return runner.spawn(children=children, **kw)


def _await_sealed(runner, swarm_id):
    for _ in range(500):
        snap = runner.snapshot(swarm_id)
        if snap and snap["status"] == "sealed":
            return snap
        time.sleep(0.01)
    raise AssertionError("the swarm never sealed")


def test_spawn_persists_a_validated_live_state(tmp_path):
    runner = SwarmRunner(run_root=tmp_path)

    class _Ok:
        @property
        def pid(self):
            return None

        def wait(self, timeout_s):
            return 0, ""

        def stop(self):
            return True

    def factory(spec_path, workspace):
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
        (Path(workspace) / "result.json").write_text(json.dumps({
            "schema": subagents.RESULT_SCHEMA,
            "spec_sha256": spec["spec_sha256"],
            "role": spec["role"], "status": "completed"}),
            encoding="utf-8")
        return _Ok()

    ack = _spawn(runner, children=[{"role": "explore"},
                                   {"role": "verify"}],
                 handle_factory=factory)
    _await_sealed(runner, ack["swarm_id"])
    live = subagents.load_live_state(
        subagents.swarm_dir(tmp_path, ack["swarm_id"]) / "live.json")
    assert live["schema"] == subagents.LIVE_SCHEMA
    assert live["swarm_id"] == ack["swarm_id"]
    assert [c["role"] for c in live["children"]] == ["explore", "verify"]
    assert all(c["workspace"] and len(c["spec_sha256"]) == 64
               for c in live["children"])


def test_snapshot_adopts_a_detached_swarm_and_seals_it(tmp_path):
    sid = "swarm_" + "a" * 12
    sdir = subagents.swarm_dir(tmp_path, sid)
    sdir.mkdir(parents=True)
    ws = sdir / "work_x"
    ws.mkdir()
    child_id = "sa_" + "b" * 8
    sha = "e" * 64
    live = {"schema": subagents.LIVE_SCHEMA, "swarm_id": sid,
            "created_at": "t", "timeout_at": time.time() + 30,
            "quorum_policy": "majority", "goal": "g", "endpoint": "dry",
            "children": [{"child_id": child_id, "role": "explore",
                          "pid": None, "workspace": str(ws),
                          "spec_sha256": sha}]}
    subagents.save_live_state(live, run_root=tmp_path)

    runner = SwarmRunner(run_root=tmp_path)
    assert runner.snapshot(sid)["status"] == "running"

    # the orphaned child finishes out-of-band; adoption notices the file
    (ws / "result.json").write_text(json.dumps({
        "schema": subagents.RESULT_SCHEMA, "spec_sha256": sha,
        "role": "explore", "status": "completed"}), encoding="utf-8")
    sealed = _await_sealed(runner, sid)
    child = sealed["receipt"]["children"][0]
    assert child["status"] == "completed" and child["reattached"] is True
    assert sealed["receipt"]["verdict"] == "satisfied"


def test_an_adopted_swarm_past_its_deadline_seals_as_timed_out(tmp_path):
    sid = "swarm_" + "c" * 12
    sdir = subagents.swarm_dir(tmp_path, sid)
    sdir.mkdir(parents=True)
    ws = sdir / "work_y"
    ws.mkdir()
    live = {"schema": subagents.LIVE_SCHEMA, "swarm_id": sid,
            "created_at": "t", "timeout_at": time.time() - 1,
            "quorum_policy": "any", "goal": "g", "endpoint": "dry",
            "children": [{"child_id": "sa_" + "d" * 8, "role": "verify",
                          "pid": None, "workspace": str(ws),
                          "spec_sha256": "f" * 64}]}
    subagents.save_live_state(live, run_root=tmp_path)

    runner = SwarmRunner(run_root=tmp_path)
    snap = runner.snapshot(sid)
    for _ in range(200):
        if snap["status"] == "sealed":
            break
        time.sleep(0.01)
        snap = runner.snapshot(sid)
    assert snap["receipt"]["children"][0]["status"] == "timeout"


def test_cancel_stops_in_process_children_and_seals_cancelled(tmp_path):
    handles = []

    def factory(spec_path, workspace):
        handle = _BlockingHandle()
        handles.append(handle)
        return handle

    runner = SwarmRunner(run_root=tmp_path)
    ack = _spawn(runner, timeout_s=30.0, handle_factory=factory)
    res = runner.cancel(ack["swarm_id"])
    assert res["state"] == "cancelled" and handles[0].stopped
    sealed = _await_sealed(runner, ack["swarm_id"])
    child = sealed["receipt"]["children"][0]
    assert child["status"] == "cancelled"
    assert sealed["receipt"]["verdict"] == "unsatisfied"


def test_cancel_kills_detached_children_by_pid_and_seals(tmp_path):
    sid = "swarm_" + "e" * 12
    sdir = subagents.swarm_dir(tmp_path, sid)
    sdir.mkdir(parents=True)
    kids = []
    for i, pid in enumerate((4242, 555)):
        ws = sdir / ("work_%d" % i)
        ws.mkdir()
        kids.append({"child_id": "sa_%08d" % i, "role": "explore",
                     "pid": pid, "workspace": str(ws),
                     "spec_sha256": "%d" % i * 64})
    live = {"schema": subagents.LIVE_SCHEMA, "swarm_id": sid,
            "created_at": "t", "timeout_at": time.time() + 60,
            "quorum_policy": "majority", "goal": "g", "endpoint": "dry",
            "children": kids}
    subagents.save_live_state(live, run_root=tmp_path)

    killed = []
    runner = SwarmRunner(run_root=tmp_path)
    res = runner.cancel(sid, killer=lambda p: (killed.append(p), True)[1])
    assert res["state"] == "cancelled" and sorted(killed) == [555, 4242]
    sealed = _await_sealed(runner, sid)
    statuses = {c["status"] for c in sealed["receipt"]["children"]}
    assert statuses == {"cancelled"}
    again = runner.cancel(sid)
    assert again.get("code") == "CANCEL_UNAVAILABLE"


def test_detached_summaries_lists_unsealed_swarms(tmp_path):
    sid = "swarm_" + "9" * 12
    sdir = subagents.swarm_dir(tmp_path, sid)
    sdir.mkdir(parents=True)
    live = {"schema": subagents.LIVE_SCHEMA, "swarm_id": sid,
            "created_at": "t", "timeout_at": time.time() + 60,
            "quorum_policy": "any", "goal": "g", "endpoint": "dry",
            "children": []}
    subagents.save_live_state(live, run_root=tmp_path)
    rows = {r["swarm_id"]: r for r in subagents.detached_summaries(tmp_path)}
    assert rows[sid]["status"] == "detached"
