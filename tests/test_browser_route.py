"""The browser control surface over HTTP.

What a caller needs from this layer is that a refused act still comes back
as a recorded verdict with a reason, that the answer never implies a screen
moved when nothing was bound to move it, and that a session whose history
was edited stops rather than continuing to judge acts.

The last test goes through `gateway._Handler` rather than calling the
handler directly, because the parity row for this capability cites the
route, and a handler nothing dispatches to is the failure that witness rule
was written to catch.
"""
import io
import json

import pytest

from harness.browser_control import chain_path, clear_drivers, register_driver
from harness.browser_route import handle_browser_get, handle_browser_post

NOW = "2026-09-06T18:00:00Z"
POLICY = {"origins": ["https://example.test"]}


@pytest.fixture(autouse=True)
def _no_driver():
    clear_drivers()
    yield
    clear_drivers()


def _clock(stamp=NOW):
    return lambda: stamp


def _run(tmp_path):
    return tmp_path / "run"


def _post(path, body, tmp_path):
    return handle_browser_post(path, body, run_root=_run(tmp_path),
                               clock=_clock())


def _get(path, tmp_path):
    return handle_browser_get(path, run_root=_run(tmp_path), clock=_clock())


def _started(tmp_path, run_id="r1", policy=None):
    _post("/api/browser/session",
          {"run_id": run_id, "policy": policy or POLICY}, tmp_path)
    return tmp_path


def test_the_surface_reads_empty_and_says_nothing_is_bound(tmp_path):
    body, code = _get("/api/browser", tmp_path)
    assert code == 200
    assert body["schema"] == "flywheel.browser-roster/v1"
    assert body["sessions"] == [] and body["driver"] is None
    assert body["read_at"] == NOW


def test_a_session_opens_navigates_and_reports_what_it_admitted(tmp_path):
    _started(tmp_path)
    body, code = _post("/api/browser/action",
                       {"run_id": "r1",
                        "action": {"kind": "navigate",
                                   "url": "https://example.test/a"}}, tmp_path)
    assert code == 200 and body["recorded"] is True
    assert body["event"]["admitted"] is True
    assert body["session"]["admitted"] == 1
    assert body["session"]["open_origin"] == "https://example.test"


def test_a_refused_act_is_recorded_rather_than_raised(tmp_path):
    """A refusal is a verdict, so it comes back 200 with the reason on it.

    Turning it into an error would leave the caller unable to tell a policy
    decision apart from a malformed request, and would leave nothing on the
    chain showing the act was ever tried.
    """
    _started(tmp_path)
    body, code = _post("/api/browser/action",
                       {"run_id": "r1",
                        "action": {"kind": "navigate",
                                   "url": "https://elsewhere.test/"}}, tmp_path)
    assert code == 200
    assert body["event"]["admitted"] is False
    assert body["event"]["reason"].endswith("is not an allowed origin")
    assert body["session"]["refused"] == 1
    assert body["session"]["performed"] == 0


def test_a_malformed_request_is_a_422_with_the_sentence(tmp_path):
    _started(tmp_path)
    body, code = _post("/api/browser/action",
                       {"run_id": "r1", "action": {"kind": "eval"}}, tmp_path)
    assert code == 422 and "unknown action kind" in body["error"]["message"]
    body, code = _post("/api/browser/action",
                       {"run_id": "r1",
                        "action": {"kind": "navigate",
                                   "url": "file:///c/secrets"}}, tmp_path)
    assert code == 422
    assert "not an http or https URL" in body["error"]["message"]


def test_a_request_that_names_no_session_is_refused(tmp_path):
    body, code = _post("/api/browser/session", {"policy": POLICY}, tmp_path)
    assert code == 422
    assert body["error"]["message"] == "run_id names the session this belongs to"
    body, code = _post("/api/browser/session", "r1", tmp_path)
    assert code == 422


def test_a_session_id_that_would_reach_another_history_is_refused(tmp_path):
    body, code = _post("/api/browser/session",
                       {"run_id": "../../etc", "policy": POLICY}, tmp_path)
    assert code == 422 and "run_id must hold" in body["error"]["message"]
    body, code = _get("/api/browser/a/b", tmp_path)
    assert code == 404


def test_the_answer_says_nothing_was_performed_when_nothing_is_bound(tmp_path):
    _started(tmp_path)
    _post("/api/browser/action",
          {"run_id": "r1", "action": {"kind": "navigate",
                                      "url": "https://example.test/"}},
          tmp_path)
    body, code = _get("/api/browser/r1", tmp_path)
    assert code == 200
    assert body["schema"] == "flywheel.browser-session/v1"
    assert body["driver"] is None and body["performed"] == 0
    assert body["admitted"] == 1
    assert body["policy"]["origins"] == ["https://example.test"]


def test_a_bound_driver_shows_up_in_both_answers(tmp_path):
    register_driver("recorder", lambda act: {"ok": True, "performed": True}, binding_sha256="a" * 64)
    _started(tmp_path)
    _post("/api/browser/action",
          {"run_id": "r1", "request_id": "one", "action": {"kind": "navigate",
                                      "url": "https://example.test/"}},
          tmp_path)
    roster, _ = _get("/api/browser", tmp_path)
    assert roster["driver"] == "recorder" and roster["sessions"] == ["r1"]
    body, _ = _get("/api/browser/r1", tmp_path)
    assert body["performed"] == 1


def test_an_edited_history_stops_the_session_rather_than_judging_on(tmp_path):
    _started(tmp_path)
    path = chain_path(_run(tmp_path), "r1")
    records = json.loads(path.read_text(encoding="utf-8"))
    records[0]["policy"]["origins"].append("https://elsewhere.test")
    path.write_text(json.dumps(records), encoding="utf-8")
    body, code = _post("/api/browser/action",
                       {"run_id": "r1",
                        "action": {"kind": "navigate",
                                   "url": "https://elsewhere.test/"}}, tmp_path)
    assert code == 422 and "broken" in body["error"]["message"]
    read, code = _get("/api/browser/r1", tmp_path)
    assert code == 200 and read["chain_intact"] is False


def test_an_unknown_browser_route_is_a_404(tmp_path):
    body, code = _post("/api/browser/close", {"run_id": "r1"}, tmp_path)
    assert code == 404 and body["error"]["message"] == "unknown browser route"
    body, code = _get("/api/browse", tmp_path)
    assert code == 404


class _FakeHeaders:
    def __init__(self, n):
        self._n = n

    def get(self, k, d=None):
        return self._n if k == "Content-Length" else d


def _handler(path, tmp_path, monkeypatch):
    import harness.gateway as gateway
    monkeypatch.setattr(gateway._Handler, "root", str(tmp_path))
    monkeypatch.setattr(gateway._Handler, "run_root", str(_run(tmp_path)))
    monkeypatch.setattr(gateway._Handler, "clock", lambda *a: NOW)
    h = gateway._Handler.__new__(gateway._Handler)
    h.path = path
    return h


def test_the_gateway_dispatches_both_browser_verbs(tmp_path, monkeypatch):
    raw = json.dumps({"run_id": "r1", "policy": POLICY}).encode()
    post = _handler("/api/browser/session", tmp_path, monkeypatch)
    post.headers = _FakeHeaders(str(len(raw)))
    post.rfile = io.BytesIO(raw)
    sent = {}
    post._json = lambda b, code=200: sent.update(body=b, code=code)
    post._post()
    assert sent["code"] == 200 and sent["body"]["recorded"] is True

    read = _handler("/api/browser", tmp_path, monkeypatch)
    seen = {}
    read._json = lambda b, code=200: seen.update(body=b, code=code)
    read._get()
    assert seen["code"] == 200 and seen["body"]["sessions"] == ["r1"]
