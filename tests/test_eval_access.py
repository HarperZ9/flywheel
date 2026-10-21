"""Access statement in the eval receipt: what the evaluator could and could not see.

Bar, written before the code (research item 3, 2026-10-21):
- every eval receipt carries an access block over six enumerated surfaces, each
  granted, not_granted or unknown; no free-text verdicts;
- the block is sealed: changing one surface changes the seal, and tampering
  with it after sealing is TAMPERED;
- a claim whose scope needs a surface the block does not record as granted is
  refused (UNVERIFIABLE, ACCESS_SHORT_OF_CLAIM), naming the surfaces, for each
  of the six scopes; a covered claim keeps MATCH;
- a receipt with no access block refuses every scoped claim (access_absent);
- false-success control: an always-covered stub would accept the training-time
  claim on an API-only run, and the real check refuses it.
"""
from __future__ import annotations

import pytest

from harness import eval_access as ea
from harness.eval_receipt import MATCH, TAMPERED, UNVERIFIABLE, build_eval_receipt, verify_eval_receipt
from harness.eval_run_route import handle_eval_verify


def _receipt(access=None, **kw):
    return build_eval_receipt(
        run_id="r", endpoint="e", model_ref="m", tasks=[{"task_id": "t"}], config={},
        judge="j", results=[{"task_id": "t", "verdict": "PASS", "accepted": True}],
        started_utc="s", finished_utc="f", access=access, **kw)


ALL = {s: "granted" for s in ea.SURFACES}


def test_six_surfaces_three_states_and_unknown_default():
    assert len(ea.SURFACES) == 6 and ea.STATES == ("granted", "not_granted", "unknown")
    blank = ea.access_statement(None)
    assert all(blank["surfaces"][s] == "unknown" for s in ea.SURFACES)
    assert blank["redacted_categories"] == "unknown" and blank["redacted_by"] == "unknown"


def test_free_text_and_unknown_surfaces_are_refused():
    with pytest.raises(ValueError):
        ea.access_statement({"surfaces": {"logits": "mostly"}})
    with pytest.raises(ValueError):
        ea.access_statement({"surfaces": {"gradients": "granted"}})


def test_api_only_default():
    a = ea.api_only()
    assert a["surfaces"]["api_outputs"] == "granted"
    assert all(a["surfaces"][s] == "not_granted" for s in ea.SURFACES if s != "api_outputs")
    assert a["redacted_categories"] == "none"


@pytest.mark.parametrize("surface", ea.SURFACES)
def test_each_surface_changes_the_seal(surface):
    flipped = {"surfaces": dict(ALL, **{surface: "not_granted"})}
    assert _receipt(flipped)["seal"]["hex"] != _receipt({"surfaces": ALL})["seal"]["hex"]


def test_tampering_with_the_block_is_caught():
    r = _receipt(ea.api_only())
    r["access"]["surfaces"]["weights"] = "granted"
    assert verify_eval_receipt(r)["verdict"] == TAMPERED


@pytest.mark.parametrize("scope", sorted(ea.CLAIM_SCOPES))
def test_scope_needing_more_access_is_refused(scope):
    need = ea.CLAIM_SCOPES[scope]
    short = {"surfaces": dict(ALL, **{need[-1]: "not_granted"})}
    v = verify_eval_receipt(_receipt(short), claim_scope=scope)
    assert v["verdict"] == UNVERIFIABLE and v["failure_class"] == "ACCESS_SHORT_OF_CLAIM"
    assert need[-1] in v["detail"]
    unknown = {"surfaces": dict(ALL, **{need[-1]: "unknown"})}
    assert verify_eval_receipt(_receipt(unknown), claim_scope=scope)["verdict"] == UNVERIFIABLE
    covered = verify_eval_receipt(_receipt({"surfaces": ALL}), claim_scope=scope)
    assert covered["verdict"] == MATCH and covered["claim_access"]["verdict"] == "PASS"


def test_api_only_run_backs_behavior_claims_only():
    r = _receipt(ea.api_only())
    assert verify_eval_receipt(r, claim_scope="output_behavior")["verdict"] == MATCH
    v = verify_eval_receipt(r, claim_scope="training_time")
    assert v["verdict"] == UNVERIFIABLE and "checkpoints" in v["detail"]


def test_receipt_without_block_refuses_scoped_claims():
    r = _receipt(None)
    del r["access"]
    from harness.tool_call_receipt import _seal_receipt
    r["seal"] = {"algorithm": "sha256", "hex": ""}
    _seal_receipt(r)
    assert verify_eval_receipt(r)["verdict"] == MATCH
    v = verify_eval_receipt(r, claim_scope="output_behavior")
    assert v["verdict"] == UNVERIFIABLE and v["claim_access"]["code"] == "access_absent"


def test_unknown_scope_is_malformed_not_a_crash():
    body, code = handle_eval_verify({"receipt": _receipt(ea.api_only()), "claim_scope": "vibes"})
    assert code == 200 and body["verdict"] == UNVERIFIABLE and body["failure_class"] == "MALFORMED"


def test_route_passes_the_scope():
    body, _ = handle_eval_verify({"receipt": _receipt(ea.api_only()),
                                  "claim_scope": "internal_state"})
    assert body["failure_class"] == "ACCESS_SHORT_OF_CLAIM"


def test_false_success_control_always_covered_stub(monkeypatch):
    r = _receipt(ea.api_only())
    monkeypatch.setattr(ea, "check_claim_access",
                        lambda access, scope: {"verdict": "PASS", "code": "stub", "missing": []})
    assert verify_eval_receipt(r, claim_scope="training_time")["verdict"] == MATCH
    monkeypatch.undo()
    assert verify_eval_receipt(r, claim_scope="training_time")["verdict"] == UNVERIFIABLE
