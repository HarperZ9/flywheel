"""The runner pool over HTTP: custody, refusals, and the wire.

The route layer is thin, so what is worth testing is the part a caller can
feel. A refusal has to arrive as the sentence that explains it rather than a
stack trace. A history that stopped verifying has to fail closed instead of
accepting the newest record on top of the break. And minting a ticket has to
sit under different custody from the routes a machine calls for itself,
because that split is the entire membership story.

The last test goes through `gateway._Handler` rather than calling the
handler directly, because the parity row for this capability cites the
route, and a handler nothing dispatches to is the failure that witness rule
was written to catch.
"""
import io
import json

from harness.gateway_custody import is_private
from harness.runner_pool import chain_path
from harness.runner_route import (handle_runners_get, handle_runners_post)

NOW = "2026-09-06T18:00:00Z"


def _clock(stamp=NOW):
    return lambda: stamp


def _run(tmp_path):
    return tmp_path / "run"


def _post(path, body, tmp_path, stamp=NOW):
    return handle_runners_post(path, body, run_root=_run(tmp_path),
                               clock=_clock(stamp))


def _pool(tmp_path):
    _post("/api/runners/tickets", {"ticket_id": "t1", "labels": ["gpu"]},
          tmp_path)
    _post("/api/runners/enroll",
          {"runner_id": "tower", "ticket_id": "t1", "labels": ["gpu"]},
          tmp_path)
    return tmp_path


def test_the_pool_reads_empty_before_any_machine_has_joined(tmp_path):
    body, code = handle_runners_get("/api/runners", run_root=_run(tmp_path),
                                    clock=_clock())
    assert code == 200
    assert body["schema"] == "flywheel.runner-roster/v1"
    assert body["runners"] == [] and body["events"] == 0
    assert body["chain_intact"] is True and body["now"] == NOW


def test_a_machine_joins_takes_work_and_reports_it_over_the_route(tmp_path):
    """The whole lifecycle, because each verb is useless without the rest."""
    _pool(tmp_path)
    body, code = _post("/api/runners/dispatch",
                       {"job_id": "train", "requires": ["gpu"]}, tmp_path)
    assert code == 200 and body["accepted"] is True
    assert body["pool"]["queued"] == 1
    body, code = _post("/api/runners/claim",
                       {"job_id": "train", "runner_id": "tower",
                        "lease_seconds": 600}, tmp_path)
    assert code == 200 and body["event"]["kind"] == "claim"
    assert body["pool"]["leased"] == 1
    body, code = _post("/api/runners/complete",
                       {"job_id": "train", "runner_id": "tower", "ok": True},
                       tmp_path)
    assert code == 200
    assert body["pool"]["jobs"][0]["state"] == "done"
    assert body["at"] == NOW


def test_a_refusal_arrives_as_the_sentence_that_explains_it(tmp_path):
    body, code = _post("/api/runners/enroll",
                       {"runner_id": "stranger", "ticket_id": "nope",
                        "labels": []}, tmp_path)
    assert code == 422
    assert body["error"]["message"] == "no ticket nope"


def test_a_field_the_verb_does_not_take_cannot_reach_it(tmp_path):
    """Bodies are read field by field rather than splatted into the verb."""
    body, code = _post("/api/runners/tickets",
                       {"ticket_id": "t1", "labels": ["gpu"],
                        "run_root": "/etc", "at": "1999-01-01T00:00:00Z"},
                       tmp_path)
    assert code == 200 and body["event"]["at"] == NOW


def test_a_body_that_is_not_an_object_is_refused(tmp_path):
    body, code = _post("/api/runners/dispatch", ["train"], tmp_path)
    assert code == 422
    assert body["error"]["message"] == "the request body must be an object"


def test_a_history_that_stopped_verifying_refuses_the_next_write(tmp_path):
    """Fail closed, because the newest record would land on top of the break.

    That is the position a reader is least likely to check, so an engine that
    keeps writing turns one edited row into a chain that looks healthy from
    the end.
    """
    _pool(tmp_path)
    path = chain_path(_run(tmp_path))
    records = json.loads(path.read_text(encoding="utf-8"))
    records[1]["labels"] = ["gpu", "secrets"]
    path.write_text(json.dumps(records), encoding="utf-8")
    body, code = _post("/api/runners/dispatch",
                       {"job_id": "train", "requires": ["gpu"]}, tmp_path)
    assert code == 409
    assert body["accepted"] is False
    assert body["refused"] == "the runner chain is broken"
    read, code = handle_runners_get("/api/runners", run_root=_run(tmp_path),
                                    clock=_clock())
    assert code == 200 and read["chain_intact"] is False


def test_an_unknown_runner_route_is_a_404(tmp_path):
    for path in ("/api/runners/promote", "/api/runners"):
        body, code = _post(path, {}, tmp_path)
        assert code == 404 and body["error"]["message"] == "unknown runner route"
    body, code = handle_runners_get("/api/runners/tower",
                                    run_root=_run(tmp_path), clock=_clock())
    assert code == 404


def test_minting_a_ticket_is_the_operators_route_and_the_rest_are_not(
        tmp_path):
    """Custody is the reason a runner cannot enlarge the pool it is in.

    The machines' own routes have to stay reachable or nothing can join or
    report; the one act deciding who may join is held back.
    """
    assert is_private("/api/runners/tickets") is True
    for path in ("/api/runners", "/api/runners/enroll", "/api/runners/claim",
                 "/api/runners/complete", "/api/runners/retire",
                 "/api/runners/dispatch"):
        assert is_private(path) is False


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


def test_the_gateway_dispatches_both_runner_verbs(tmp_path, monkeypatch):
    raw = json.dumps({"ticket_id": "t1", "labels": ["gpu"]}).encode()
    post = _handler("/api/runners/tickets", tmp_path, monkeypatch)
    post.headers = _FakeHeaders(str(len(raw)))
    post.rfile = io.BytesIO(raw)
    sent = {}
    post._json = lambda b, code=200: sent.update(body=b, code=code)
    post._post()
    assert sent["code"] == 200 and sent["body"]["accepted"] is True

    read = _handler("/api/runners", tmp_path, monkeypatch)
    seen = {}
    read._json = lambda b, code=200: seen.update(body=b, code=code)
    read._get()
    assert seen["code"] == 200
    assert seen["body"]["tickets_unspent"] == 1
