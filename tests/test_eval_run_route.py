"""Tests for the eval-run route (run + verify), socketless and model-free.

run_verified and the proposer factory are substituted, so the whole route runs
with no real model and no network: the task set materializes for real (offline),
each task's disposition is faked, and the receipt is sealed and re-checked. The
gateway's thin dispatch stubs are exercised through the same in-process handler
pattern tests/test_gateway.py uses.
"""
from __future__ import annotations

import io
import json

from harness import eval_run_route
from harness.eval_receipt import MATCH, TAMPERED, UNVERIFIABLE


class _FakeProposer:
    model_ref = "fake:model"

    def generate(self, *a, **k):  # pragma: no cover - must never be reached
        raise AssertionError("the proposer must not be called when run_verified is faked")


class _FakeEV:
    def __init__(self, verdict="PASS", accepted=True):
        self.verdict = verdict
        self.accepted = accepted
        self.loop = None


def _patch(monkeypatch, roster=None):
    """Substitute the roster, the proposer factory, and run_verified. Returns
    the list that records which task_ids run_verified was asked to dispose."""
    roster = roster or {
        "endpoints": [{"name": "stub", "credential": "present"}],
        "usable_names": ["stub"],
    }
    monkeypatch.setattr(eval_run_route, "unified_roster", lambda: roster)
    monkeypatch.setattr(eval_run_route, "make_endpoint_proposer",
                        lambda name, **k: _FakeProposer())
    calls: list[str] = []

    def fake_run_verified(task, prop, *, domain, **kw):
        calls.append(task.task_id)
        assert domain == "code"
        return _FakeEV("PASS", True)

    monkeypatch.setattr(eval_run_route, "run_verified", fake_run_verified)
    return calls


# --- direct handler tests ---------------------------------------------------


def test_run_then_verify_round_trips_match(tmp_path, monkeypatch):
    _patch(monkeypatch)
    body, code = eval_run_route.handle_eval_run(
        {"endpoint": "stub", "n": 3}, tmp_path)
    assert code == 200
    assert len(body["results"]) == 3
    # the receipt file is a BARE filename, never an absolute path
    rf = body["receipt_file"]
    assert rf and "/" not in rf and "\\" not in rf and ":" not in rf
    v, vcode = eval_run_route.handle_eval_verify({"receipt": body["receipt"]})
    assert vcode == 200
    assert v["verdict"] == MATCH


def test_corrupt_one_byte_is_refused(tmp_path, monkeypatch):
    _patch(monkeypatch)
    body, _ = eval_run_route.handle_eval_run({"endpoint": "stub", "n": 2}, tmp_path)
    # corrupt a COPY, never the emitted receipt
    receipt = json.loads(json.dumps(body["receipt"]))
    hx = list(receipt["seal"]["hex"])
    hx[0] = "0" if hx[0] != "0" else "1"
    receipt["seal"]["hex"] = "".join(hx)
    v, vcode = eval_run_route.handle_eval_verify({"receipt": receipt})
    assert vcode == 200
    assert v["verdict"] == TAMPERED
    assert v["failure_class"] == "SEAL_MISMATCH"


def test_missing_endpoint_is_400(tmp_path, monkeypatch):
    _patch(monkeypatch)
    body, code = eval_run_route.handle_eval_run({}, tmp_path)
    assert code == 400
    assert "endpoint" in body["error"]


def test_unknown_endpoint_is_404(tmp_path, monkeypatch):
    _patch(monkeypatch, roster={"endpoints": [], "usable_names": []})
    body, code = eval_run_route.handle_eval_run({"endpoint": "nope"}, tmp_path)
    assert code == 404
    assert "usable" in body


def test_absent_credential_is_400(tmp_path, monkeypatch):
    _patch(monkeypatch, roster={
        "endpoints": [{"name": "stub", "credential": "absent"}],
        "usable_names": []})
    body, code = eval_run_route.handle_eval_run({"endpoint": "stub"}, tmp_path)
    assert code == 400
    assert body["credential"] == "absent"


def test_n_is_capped_at_five(tmp_path, monkeypatch):
    calls = _patch(monkeypatch)
    body, code = eval_run_route.handle_eval_run(
        {"endpoint": "stub", "n": 99}, tmp_path)
    assert code == 200
    assert len(body["results"]) == 5
    assert len(calls) == 5


def test_provider_failure_is_502(tmp_path, monkeypatch):
    _patch(monkeypatch)

    def boom(task, prop, *, domain, **kw):
        raise RuntimeError("provider unreachable")

    monkeypatch.setattr(eval_run_route, "run_verified", boom)
    body, code = eval_run_route.handle_eval_run({"endpoint": "stub"}, tmp_path)
    assert code == 502
    assert "provider call failed" in body["error"]


def test_verify_of_missing_receipt_is_unverifiable(tmp_path):
    v, code = eval_run_route.handle_eval_verify({})
    assert code == 200
    assert v["verdict"] == UNVERIFIABLE


# --- gateway dispatch tests (the thin stubs) --------------------------------


class _Headers:
    def __init__(self, cl):
        self._cl = cl

    def get(self, key, default=None):
        return self._cl if key == "Content-Length" else default


def _dispatch(path: str, body: dict, run_root):
    from harness import gateway
    raw = json.dumps(body).encode()
    h = gateway._Handler.__new__(gateway._Handler)
    h.path = path
    h.root = "."
    h.run_root = str(run_root)
    h.headers = _Headers(str(len(raw)))
    h.rfile = io.BytesIO(raw)
    sent: dict = {}
    h._json = lambda b, code=200: sent.update(body=b, code=code)
    h._post()
    return sent


def test_gateway_dispatch_run_and_verify(tmp_path, monkeypatch):
    _patch(monkeypatch)
    ran = _dispatch("/api/eval/run", {"endpoint": "stub", "n": 2}, tmp_path)
    assert ran["code"] == 200
    receipt = ran["body"]["receipt"]
    checked = _dispatch("/api/eval/verify", {"receipt": receipt}, tmp_path)
    assert checked["code"] == 200
    assert checked["body"]["verdict"] == MATCH


def test_gateway_dispatch_run_missing_endpoint_is_400(tmp_path, monkeypatch):
    _patch(monkeypatch)
    ran = _dispatch("/api/eval/run", {}, tmp_path)
    assert ran["code"] == 400
