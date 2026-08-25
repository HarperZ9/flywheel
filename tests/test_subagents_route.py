"""The subagent swarm routes: listing, snapshot polling, and spawning.
Spawn returns immediately with children running; the sealed fan-in
receipt persists under the run root."""
import json
import time
from pathlib import Path

from harness import subagents


class _FakeHeaders:
    def __init__(self, n):
        self._n = n

    def get(self, k, d=None):
        return self._n if k == "Content-Length" else d


def _post(path, body):
    import io

    import harness.gateway as gateway
    raw = json.dumps(body).encode()
    h = gateway._Handler.__new__(gateway._Handler)
    h.path = path
    h.headers = _FakeHeaders(str(len(raw)))
    h.rfile = io.BytesIO(raw)
    sent = {}
    h._json = lambda b, code=200: sent.update(body=b, code=code)
    h._post()
    return sent


def _get(path):
    import harness.gateway as gateway
    h = gateway._Handler.__new__(gateway._Handler)
    h.path = path
    h.headers = _FakeHeaders("0")
    sent = {}
    h._json = lambda b, code=200: sent.update(body=b, code=code)
    h._get()
    return sent


class _FastHandle:
    def wait(self, timeout_s):
        time.sleep(0.02)
        return 0, ""

    def stop(self):
        return True


def _fast_factory(spec_path, workspace):
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    (Path(workspace) / "result.json").write_text(json.dumps({
        "schema": subagents.RESULT_SCHEMA,
        "spec_sha256": spec["spec_sha256"],
        "role": spec["role"], "status": "completed"}), encoding="utf-8")
    return _FastHandle()


def _setup(tmp_path, monkeypatch):
    import harness.gateway as gateway
    monkeypatch.setattr(gateway._Handler, "run_root", str(tmp_path))
    monkeypatch.setattr(gateway._Handler, "owner_ref", "owner_" + "a" * 32)
    monkeypatch.setattr(gateway._Handler, "flywheel_home", tmp_path)
    monkeypatch.setattr(gateway._Handler, "clock",
                        lambda *a: "2026-08-24T12:00:00Z")
    monkeypatch.setattr(subagents, "popen_handle", _fast_factory)


def _await_sealed(swarm_id):
    for _ in range(500):
        snap = _get("/api/subagents/swarm?id=" + swarm_id)
        if snap["code"] == 200 and snap["body"].get("status") == "sealed":
            return snap
        time.sleep(0.01)
    raise AssertionError("the swarm never sealed")


def test_spawn_round_trip_lists_and_seals(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    sent = _post("/api/subagents/spawn",
                 {"goal": "map the auth module", "endpoint": "dry",
                  "children": ["explore", {"role": "verify"}]})
    assert sent["code"] == 200
    assert sent["body"]["schema"] == "flywheel.subagent-spawn-ack/v1"
    assert sent["body"]["status"] == "running"
    swarm_id = sent["body"]["swarm_id"]

    snap = _await_sealed(swarm_id)
    receipt = snap["body"]["receipt"]
    assert receipt["verdict"] == "satisfied"
    assert receipt["total"] == 2

    listed = _get("/api/subagents")
    assert listed["code"] == 200
    ids = {row["swarm_id"] for row in listed["body"]["swarms"]}
    assert swarm_id in ids


def test_spawn_refuses_an_unusable_request(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    sent = _post("/api/subagents/spawn",
                 {"goal": "", "endpoint": "dry",
                  "children": ["explore"]})
    assert sent["code"] == 422
    sent = _post("/api/subagents/spawn",
                 {"goal": "g", "endpoint": "dry",
                  "children": [{"role": "explore", "allow_write": True}]})
    assert sent["code"] == 422


def test_unknown_swarm_is_404(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    sent = _get("/api/subagents/swarm?id=swarm_" + "0" * 12)
    assert sent["code"] == 404


def test_unknown_subagent_route_is_404(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert _post("/api/subagents/explode", {})["code"] == 404
    assert _get("/api/subagents/explode")["code"] == 404
