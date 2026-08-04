"""Tests for the audit-run route (run + verify), socketless and model-free.

make_endpoint_proposer is substituted so the optional model narrative needs no
real model and no network; the deterministic detectors run for real over a sealed
work receipt. The gateway's thin dispatch stubs are exercised through the same
in-process handler pattern tests/test_gateway.py uses.
"""
from __future__ import annotations

import io
import json

from harness import audit_run_route
from harness.audit_receipt import MATCH, TAMPERED
from harness.proposer import ProposerOutput
from harness.tool_call_receipt import build_receipt


class _FakeProposer:
    model_ref = "fake:model"

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        return ProposerOutput(text="Look at the integrity finding first.",
                              model_ref=self.model_ref, seed=seed,
                              prompt_hash="", cache="stub")


def _work_receipt():
    return build_receipt(
        tool="write", capability="builtin-write", admission="ALLOWED",
        args={"path": "x"}, output="done", ok=True, rc=0, run_id="w1", seq=1)


# --- direct handler tests ---------------------------------------------------


def test_run_then_verify_round_trips_match(tmp_path):
    work = _work_receipt()
    body, code = audit_run_route.handle_audit_run({"work_receipt": work}, tmp_path)
    assert code == 200
    assert body["verdict"] in ("PASS", "CONCERNS", "FAIL")
    assert body["detectors"] == list(audit_run_route._STARTER_DETECTORS)
    # the receipt file is a BARE filename, never an absolute path
    rf = body["receipt_file"]
    assert rf and "/" not in rf and "\\" not in rf and ":" not in rf
    v, vcode = audit_run_route.handle_audit_verify({"audit_receipt": body["receipt"]})
    assert vcode == 200
    assert v["verdict"] == MATCH


def test_audit_chains_onto_the_work_receipt(tmp_path):
    work = _work_receipt()
    body, _ = audit_run_route.handle_audit_run({"work_receipt": work}, tmp_path)
    receipt = body["receipt"]
    # the chain link IS the work receipt's seal hex
    assert receipt["prev_receipt_sha256"] == work["seal"]["hex"]
    v, _ = audit_run_route.handle_audit_verify(
        {"audit_receipt": receipt, "work_receipt": work})
    assert v["verdict"] == MATCH
    # a wrong work receipt breaks the chain
    other = build_receipt(tool="read", capability="builtin-read", admission="ALLOWED",
                          args={}, output="y", ok=True, rc=0, run_id="w2", seq=1)
    vb, _ = audit_run_route.handle_audit_verify(
        {"audit_receipt": receipt, "work_receipt": other})
    assert vb["verdict"] == TAMPERED
    assert vb["failure_class"] == "CHAIN_BROKEN"


def test_corrupt_one_byte_is_refused(tmp_path):
    work = _work_receipt()
    body, _ = audit_run_route.handle_audit_run({"work_receipt": work}, tmp_path)
    receipt = json.loads(json.dumps(body["receipt"]))  # corrupt a COPY
    hx = list(receipt["seal"]["hex"])
    hx[0] = "0" if hx[0] != "0" else "1"
    receipt["seal"]["hex"] = "".join(hx)
    v, vcode = audit_run_route.handle_audit_verify({"audit_receipt": receipt})
    assert vcode == 200
    assert v["verdict"] == TAMPERED
    assert v["failure_class"] == "SEAL_MISMATCH"


def test_missing_work_receipt_is_400(tmp_path):
    body, code = audit_run_route.handle_audit_run({}, tmp_path)
    assert code == 400
    assert "work_receipt" in body["error"]


def test_non_dict_work_receipt_is_400(tmp_path):
    body, code = audit_run_route.handle_audit_run({"work_receipt": "nope"}, tmp_path)
    assert code == 400


def test_offline_is_deterministic_with_an_honest_null_summary(tmp_path):
    work = _work_receipt()
    body, code = audit_run_route.handle_audit_run({"work_receipt": work}, tmp_path)
    assert code == 200
    assert body["narrated"] is False
    assert body["reviewer"] == "flywheel-audit/starter"
    assert body["does_not_prove"].strip()  # the honest null is never empty
    assert "deterministic" in body["summary"] or body["summary"].startswith("verdict")


def test_tampered_work_receipt_fails_with_high_confidence(tmp_path):
    work = _work_receipt()
    tampered = json.loads(json.dumps(work))
    hx = list(tampered["seal"]["hex"])
    hx[0] = "0" if hx[0] != "0" else "1"
    tampered["seal"]["hex"] = "".join(hx)
    body, code = audit_run_route.handle_audit_run({"work_receipt": tampered}, tmp_path)
    assert code == 200
    assert body["verdict"] == "FAIL"
    assert body["confidence"] == "high"
    assert body["reviews"][0]["detector_id"] == "receipt_integrity"
    assert body["reviews"][0]["severity"] == "CRITICAL"


def test_unbacked_claim_is_flagged_from_the_artifact(tmp_path):
    work = _work_receipt()
    body, _ = audit_run_route.handle_audit_run(
        {"work_receipt": work, "artifact": "I already ran the full suite."}, tmp_path)
    ids = {r["detector_id"] for r in body["reviews"]}
    assert "unbacked_claim" in ids
    assert body["verdict"] == "CONCERNS"


def test_model_narrative_is_used_when_a_proposer_is_supplied(tmp_path, monkeypatch):
    monkeypatch.setattr(audit_run_route, "make_endpoint_proposer",
                        lambda name, **k: _FakeProposer())
    work = _work_receipt()
    body, code = audit_run_route.handle_audit_run(
        {"work_receipt": work, "endpoint": "stub"}, tmp_path)
    assert code == 200
    assert body["narrated"] is True
    assert body["summary"] == "Look at the integrity finding first."
    assert body["reviewer"] == "flywheel-audit/starter+fake:model"


def test_unreachable_narrator_degrades_to_an_honest_null(tmp_path, monkeypatch):
    def boom(name, **k):
        raise RuntimeError("no such endpoint here")
    monkeypatch.setattr(audit_run_route, "make_endpoint_proposer", boom)
    work = _work_receipt()
    body, code = audit_run_route.handle_audit_run(
        {"work_receipt": work, "endpoint": "stub"}, tmp_path)
    assert code == 200  # a missing narrator is never a 502
    assert body["narrated"] is False
    assert "deterministic" in body["does_not_prove"]


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


def test_gateway_dispatch_run_and_verify(tmp_path):
    work = _work_receipt()
    ran = _dispatch("/api/audit/run", {"work_receipt": work}, tmp_path)
    assert ran["code"] == 200
    receipt = ran["body"]["receipt"]
    checked = _dispatch("/api/audit/verify",
                        {"audit_receipt": receipt, "work_receipt": work}, tmp_path)
    assert checked["code"] == 200
    assert checked["body"]["verdict"] == MATCH


def test_gateway_dispatch_run_missing_work_receipt_is_400(tmp_path):
    ran = _dispatch("/api/audit/run", {}, tmp_path)
    assert ran["code"] == 400
