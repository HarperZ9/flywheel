"""The accountable hooks routes: registry listing, exact-grant
registration, and exact-grant firing. Registration and execution are
separate authorities; the registry persists under the run root; a
failing blocking hook marks the event blocked."""
import json

from harness.hooks_route import handle_hooks_get, handle_hooks_post


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


ARGS = ["python", "-c", "print('teeth')"]


def test_hooks_register_and_list_round_trip(tmp_path, monkeypatch):
    import harness.gateway as gateway
    monkeypatch.setattr(gateway._Handler, "run_root", str(tmp_path))
    monkeypatch.setattr(gateway._Handler, "owner_ref", "owner_" + "a" * 32)
    monkeypatch.setattr(gateway._Handler, "flywheel_home", tmp_path)
    monkeypatch.setattr(gateway._Handler, "clock",
                        lambda *a: "2026-08-24T12:00:00Z")

    sent = _post("/api/hooks/register",
                 {"event": "bench.completed", "argv": ARGS,
                  "blocking": True, "hook_id": "hook_" + "a" * 8})
    assert sent["code"] == 200
    assert sent["body"]["hook"]["hook_id"] == "hook_" + "a" * 8

    listed = _get("/api/hooks")
    assert listed["code"] == 200
    assert listed["body"]["count"] == 1
    assert listed["body"]["hooks"][0]["argv"] == ARGS


def test_hooks_register_refuses_a_secret_shaped_command(tmp_path,
                                                        monkeypatch):
    import harness.gateway as gateway
    monkeypatch.setattr(gateway._Handler, "run_root", str(tmp_path))
    monkeypatch.setattr(gateway._Handler, "owner_ref", "owner_" + "a" * 32)
    monkeypatch.setattr(gateway._Handler, "flywheel_home", tmp_path)
    monkeypatch.setattr(gateway._Handler, "clock",
                        lambda *a: "2026-08-24T12:00:00Z")
    sent = _post("/api/hooks/register",
                 {"event": "bench.completed",
                  "argv": ["python", "-c", "read the API_KEY"],
                  "blocking": False, "hook_id": "hook_" + "b" * 8})
    assert sent["code"] == 422


def test_hooks_run_fires_and_reports_blocked(tmp_path, monkeypatch):
    import harness.gateway as gateway
    monkeypatch.setattr(gateway._Handler, "run_root", str(tmp_path))
    monkeypatch.setattr(gateway._Handler, "owner_ref", "owner_" + "a" * 32)
    monkeypatch.setattr(gateway._Handler, "flywheel_home", tmp_path)
    monkeypatch.setattr(gateway._Handler, "clock",
                        lambda *a: "2026-08-24T12:00:00Z")
    _post("/api/hooks/register",
          {"event": "bench.completed",
           "argv": ["python", "-c", "import sys; sys.exit(3)"],
           "blocking": True, "hook_id": "hook_" + "c" * 8})
    sent = _post("/api/hooks/run",
                 {"event": "bench.completed",
                  "context": {"bench_sha256": "a" * 64}})
    assert sent["code"] == 200
    assert sent["body"]["event_blocked"] is True
    assert sent["body"]["hook_receipts"][0]["exit_code"] == 3


def test_unknown_hook_route_is_404(tmp_path):
    sent = _post("/api/hooks/explode", {})
    assert sent["code"] == 404
