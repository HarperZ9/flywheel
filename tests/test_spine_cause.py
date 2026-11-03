"""Cause-and-effect fields, and the false accepts the verifier must refuse.

A matched-twin claim is only worth anything if a twin that differs in a second
field, or an effect that does not follow from the twin, is caught. Each refusal
test below is a receipt a careless or motivated writer could produce, sealed
correctly, so the seal alone would pass it.
"""
import copy
import json
from pathlib import Path

import pytest

from harness.spine import check_cause, from_native, verify_record
from harness.spine import natives
from harness.spine.record import digest
from harness.verdict import Verdict

FIXTURES = Path(__file__).parent / "fixtures" / "spine"
BASE = {"model": "m-1", "seed": 7, "task_set": "t-40", "temperature": 0.0}


def _cause(**over):
    twin = {"inputs": dict(BASE), "outcome": 0.70}
    run = {"inputs": dict(BASE, temperature=0.7), "outcome": 0.82}
    placebo = {"change": {"field": "agent_name", "value": "renamed"},
               "run": {"inputs": dict(BASE, agent_name="renamed"), "outcome": 0.71},
               "effect": 0.71 - 0.70,
               "interval": {"low": -0.03, "high": 0.05, "level": 0.95}}
    cause = {"intervention": {"field": "temperature", "value": 0.7, "twin_value": 0.0},
             "run": run, "twin": twin, "twin_digest": digest(twin),
             "effect": 0.82 - 0.70,
             "interval": {"low": 0.05, "high": 0.19, "level": 0.95,
                          "method": "seed bootstrap, 1000 resamples"},
             "placebo": placebo}
    cause.update(over)
    return cause


def _verdicts(cause):
    return {name: verdict for name, verdict, _ in check_cause(cause)}


def _worst(cause):
    from harness.spine.vocab import fold
    return fold(v for _, v, _ in check_cause(cause))


def test_a_complete_matched_twin_receipt_passes_every_cause_check():
    verdicts = _verdicts(_cause())
    assert set(verdicts.values()) == {Verdict.PASS}
    assert {"cause.twin", "cause.pairing", "cause.effect", "cause.interval",
            "cause.placebo.interval"} <= set(verdicts)


def test_false_accept_a_twin_that_differs_in_two_fields_is_refused():
    cause = _cause()
    cause["twin"]["inputs"]["model"] = "m-2"   # a second, undeclared difference
    cause["twin_digest"] = digest(cause["twin"])
    verdicts = _verdicts(cause)
    assert verdicts["cause.pairing"] is Verdict.FAIL
    detail = next(d for n, _, d in check_cause(cause) if n == "cause.pairing")
    assert "model" in detail and "temperature" in detail


def test_false_accept_an_effect_that_does_not_match_its_twin_is_refused():
    verdicts = _verdicts(_cause(effect=0.30))
    assert verdicts["cause.effect"] is Verdict.FAIL


def test_false_accept_a_twin_swapped_after_sealing_is_refused():
    cause = _cause()
    cause["twin"] = {"inputs": dict(BASE), "outcome": 0.52}   # digest not updated
    assert _verdicts(cause)["cause.twin"] is Verdict.FAIL


def test_false_accept_declared_values_the_runs_did_not_use_are_refused():
    cause = _cause(intervention={"field": "temperature", "value": 1.0, "twin_value": 0.0})
    assert _verdicts(cause)["cause.intervention"] is Verdict.FAIL


def test_false_accept_an_interval_that_excludes_its_own_effect_is_refused():
    cause = _cause(interval={"low": 0.20, "high": 0.30, "level": 0.95})
    assert _verdicts(cause)["cause.interval"] is Verdict.FAIL


def test_an_effect_without_a_twin_digest_is_unverifiable():
    cause = _cause()
    del cause["twin_digest"]
    assert _worst(cause) is Verdict.UNVERIFIABLE


def test_a_digest_with_no_embedded_twin_is_unverifiable():
    cause = _cause()
    del cause["twin"]
    assert _verdicts(cause)["cause.twin"] is Verdict.UNVERIFIABLE


def test_a_placebo_that_moves_the_outcome_marks_the_pairing_confounded():
    cause = _cause()
    cause["placebo"].update(run={"inputs": dict(BASE, agent_name="renamed"), "outcome": 0.80},
                            effect=0.80 - 0.70,
                            interval={"low": 0.04, "high": 0.16, "level": 0.95})
    verdicts = _verdicts(cause)
    assert verdicts["cause.placebo.interval"] is Verdict.UNVERIFIABLE
    assert "CONFOUNDED" in next(d for n, _, d in check_cause(cause)
                                if n == "cause.placebo.interval")


def test_a_placebo_that_changes_a_real_input_is_refused():
    cause = _cause()
    cause["placebo"]["run"]["inputs"]["temperature"] = 0.7
    assert _verdicts(cause)["cause.placebo"] is Verdict.FAIL


@pytest.mark.parametrize("field", ["interval", "placebo"])
def test_interval_and_placebo_are_optional(field):
    cause = _cause()
    del cause[field]
    assert _worst(cause) is Verdict.PASS


def test_a_cause_block_rides_on_a_tool_receipt_and_is_sealed_with_it():
    payload = json.loads((FIXTURES / "crucible-assessment-warn.json").read_text(encoding="utf-8"))
    record = from_native(natives.CRUCIBLE, payload, cause=_cause())
    result = verify_record(record)
    assert result.verdict is Verdict.PASS, result.checks
    forged = copy.deepcopy(record)
    forged["cause"]["effect"] = 0.5
    assert verify_record(forged).verdict is Verdict.FAIL   # seal and effect both break
