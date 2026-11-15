"""Claim grounding: the summary is checked against the ledger, not just the chain.

Load-bearing: an intact chain with a lying summary ("all tests pass" over a failed
check) is REFUTED -- the node no competitor inspects.
"""
from relay.claim_grounding import (
    GROUNDED,
    REFUTED,
    UNGROUNDED,
    UNVERIFIABLE,
    extract_claims,
    ground_claims,
    ground_final_answer,
)
from relay.local_session import SessionLedger


def _led(*entries):
    led = SessionLedger()
    for kind, content, *meta in entries:
        led.append(kind, content, meta[0] if meta else None)
    return led


def test_summary_claiming_pass_over_a_failed_check_is_refuted():
    led = _led(("user", "fix it"),
               ("tool_call", 'run {"cmd": "pytest"}'),
               ("check", "[exit 1]\n1 failed", {"cmd": "pytest -q", "ok": False}),
               ("assistant", "Fixed the null bug; all tests pass."))
    out = ground_claims(extract_claims("Fixed the null bug; all tests pass."), led)
    assert out["verdict"] == REFUTED


def test_claim_naming_an_untouched_file_is_ungrounded():
    led = _led(("user", "refactor"),
               ("assistant", "Refactored widget.py for clarity."))  # widget.py never edited
    out = ground_claims(extract_claims("Refactored widget.py for clarity."), led)
    assert out["verdict"] == UNGROUNDED


def test_honest_claim_with_a_witness_is_grounded():
    led = _led(("user", "fix parser"),
               ("tool_call", 'edit_file {"path": "parser.py", "old": "a", "new": "b"}'),
               ("check", "[exit 0]\n3 passed", {"cmd": "pytest -q", "ok": True}),
               ("assistant", "Edited parser.py; tests pass."))
    out = ground_claims(extract_claims("Edited parser.py; tests pass."), led)
    assert out["verdict"] == GROUNDED
    assert out["grounded_ratio"] == 1.0


def test_unparseable_claim_is_unclassified_never_a_silent_pass():
    out = ground_claims(extract_claims("It works now."), _led(("user", "go")))
    assert any(f["status"] == "unclassified" for f in out["findings"])
    assert out["verdict"] == UNVERIFIABLE  # fail-closed, not GROUNDED


def test_claiming_failure_over_a_passing_check_is_also_refuted():
    led = _led(("check", "[exit 0]\nok", {"cmd": "pytest", "ok": True}),
               ("assistant", "The tests still fail."))
    out = ground_claims(extract_claims("The tests still fail."), led)
    assert out["verdict"] == REFUTED


def test_ground_final_answer_reads_the_last_assistant_turn():
    led = _led(("user", "fix parser"),
               ("tool_call", 'edit_file {"path": "parser.py", "old": "a", "new": "b"}'),
               ("assistant", "Working on parser.py."),
               ("check", "[exit 0]", {"cmd": "pytest", "ok": True}),
               ("assistant", "Edited parser.py; tests pass."))
    out = ground_final_answer(led)
    assert out["verdict"] == GROUNDED and out["seq"] == 4


def test_extract_classifies_test_verdict_change_and_vague():
    kinds = [c.kind for c in extract_claims(
        "Edited app.py. All tests pass. Looks good to me.")]
    assert kinds == ["file_change", "test_verdict", "vague"]
