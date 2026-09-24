"""Acceptance tests for the decide lane's /v1/systemone wire contract (design 5.5, Contract)."""
import copy
import hashlib
import json

import pytest

from harness import decision_contract
from harness import systemone_contract as so
from harness.evidence_json import canonical_bytes

MARKER = "MARKER-7f3a-do-not-echo"


def _hex(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def _doc_request() -> dict:
    """The documented request example (design 4.4), verbatim apart from the state text."""
    return {
        "model": "auto:file_relevance",
        "state": "Record scorer exception types in the workflow adapter.",
        "questions": {"q1": {
            "type": "noul",
            "instructions": "Does the change described in the state require editing "
                            "harness/classifier_workflows.py (shared advisory scoring adapter)?",
            "criteria": {"true": "must be edited", "false": "can stay unchanged"}}},
        "x_flywheel": {
            "task_family": "file_relevance", "mode": "shadow", "sensitivity": "public",
            "abstain_mode": "strict", "act_on": {"q1": ["false"]}, "none_option": True,
            "invariants": [], "deadline_ms": 2000}}


def _doc_response() -> dict:
    """The documented response example; the elided hashes are filled with real hex."""
    return {
        "model": "readout:qwen2.5-coder-14b-nf4@" + _hex("weights")[:12],
        "answers": {"q1": {"type": "noul", "noul": None}},
        "usage": {"input_tokens": 2143, "output_tokens": 0},
        "x_flywheel": {
            "decisions": {"q1": {
                "action": "abstain", "reason": "below_threshold",
                "raw": {"true": 0.18, "false": 0.80, "none": 0.02},
                "p_none": 0.02, "correct_prob": 0.83, "order_agreement": True,
                "label_mass": 0.97, "prediction_set": None}},
            "policy_card_sha256": _hex("card"),
            "certification": {"alpha": 0.05, "delta": 0.05, "n_units": 250,
                              "upper_error_bound": 0.043,
                              "status": "statistical_candidate_only"},
            "receipt": {
                "schema": "flywheel.decision-receipt/v1", "request_sha256": _hex("request"),
                "prompt_sha256": {"q1": _hex("prompt")}, "backend": "readout",
                "model_id": "qwen2.5-coder-14b-nf4", "weights_sha256": _hex("weights"),
                "code_commit": "91dfd406d", "cache_path": "prefix_tree", "reads": 2,
                "latency_ms": {"queue": 1, "prefill": 38, "read": 22}, "gpu_seconds": 0.06,
                "cost_usd": None,
                "does_not_prove": "Correctness of any single decision, authorization, or "
                                  "exchangeability of future items."}}}


def _choice(n: int, *, none_option: bool = True) -> dict:
    return {"model": "auto:f1", "state": "s",
            "questions": {"q": {"type": "choice", "instructions": "Pick one.",
                                "criteria": {f"o{i}": f"option {i}" for i in range(n)}}},
            "x_flywheel": {"none_option": none_option}}


def _code(payload, **kwargs) -> str:
    with pytest.raises(so.SystemOneError) as info:
        so.validate_request(payload, **kwargs)
    assert info.value.status == 422 and info.value.code in so.ERROR_CODES
    return info.value.code


def _decision_request(eligible=("local", "hosted")) -> dict:
    return {
        "schema": "flywheel.decision-request/v1", "decision_ref": "route_1",
        "state": "Choose the safest route.",
        "choices": [{"id": "local", "description": "Use the local model."},
                    {"id": "hosted", "description": "Use a hosted endpoint."},
                    {"id": "skip", "description": "Skip the step."}],
        "eligible_choice_ids": list(eligible), "evidence_refs": ["ev_roster"]}


def test_documented_request_round_trips_unchanged_and_is_independent():
    payload = _doc_request()
    snap = so.validate_request(payload)
    assert snap == _doc_request() and json.dumps(snap) == json.dumps(_doc_request())
    assert so.parse_request(json.dumps(payload).encode()) == _doc_request()
    payload["questions"]["q1"]["criteria"]["true"] = "mutated"
    assert snap["questions"]["q1"]["criteria"]["true"] == "must be edited"
    assert canonical_bytes(so.validate_request(snap)) == canonical_bytes(snap)


def test_documented_response_round_trips_unchanged_against_its_request():
    request = so.validate_request(_doc_request())
    snap = so.validate_response(_doc_response(), request)
    assert snap == _doc_response() and json.dumps(snap) == json.dumps(_doc_response())
    assert so.validate_response(snap) == _doc_response()
    raw = snap["x_flywheel"]["decisions"]["q1"]["raw"]
    rendered = so.render_answer(request["questions"]["q1"], raw, {"action": "abstain"})
    assert rendered == snap["answers"]["q1"] == {"type": "noul", "noul": None}


@pytest.mark.parametrize("payload, code", [
    (_choice(63), "too_many_options"),
    (_choice(63, none_option=False), "too_many_options"),
    (_choice(62), "too_many_options"),
    ({"model": "m", "state": "s", "questions": {}}, "schema_invalid"),
    ({"model": "m", "state": "s", "questions": {"q": {"type": "rank", "instructions": "x"}}},
     "schema_invalid"),
    ({"model": "m", "state": "s",
      "questions": {"q": {"type": "score", "instructions": "x", "criteria": ["only"]}}},
     "schema_invalid"),
    ({"model": "m", "state": "s", "questions": {"q": {
        "type": "score", "instructions": "x", "criteria": [str(i) for i in range(11)]}}},
     "too_many_options"),
])
def test_bad_requests_return_422_with_the_fixed_code(payload, code):
    assert _code(payload) == code


def test_label_budget_boundary_counts_the_none_label():
    assert len(so.validate_request(_choice(61))["questions"]["q"]["criteria"]) == 61
    assert len(so.validate_request(_choice(62, none_option=False))["questions"]["q"]
               ["criteria"]) == 62
    ten = {"model": "m", "state": "s", "questions": {"q": {
        "type": "score", "instructions": "x", "criteria": [str(i) for i in range(10)]}}}
    assert so.answer_labels(so.validate_request(ten)["questions"]["q"])[-1] == "9"


def test_other_fixed_codes_fire_on_their_own_conditions():
    colliding = _choice(2)
    colliding["questions"]["q"]["criteria"]["__none__"] = "nothing"
    assert _code(colliding) == "label_collision"
    assert _code({**_choice(2), "state": "x" * so.DEFAULT_MAX_INPUT_CHARS}) == "state_too_long"
    assert _code(_choice(2), served_models={"auto:f2"}) == "unknown_model"
    assert _code({**_choice(2), "x_flywheel": {"task_family": "f2"}}) == "schema_invalid"
    assert _code({**_choice(2), "extra": 1}) == "schema_invalid"
    bad_act = _doc_request()
    bad_act["x_flywheel"]["act_on"] = {"q1": ["maybe"]}
    assert _code(bad_act) == "schema_invalid"
    bad_inv = _choice(2)
    bad_inv["x_flywheel"]["invariants"] = [{"kind": "exclusive", "questions": ["q", "q"]}]
    assert _code(bad_inv) == "schema_invalid"


def test_errors_never_echo_request_content():
    long_state = {**_choice(2), "state": MARKER * 5000}
    dup_key = ('{"model": "m", "state": "s", "questions": {}, "questions": {"' + MARKER + '": 1}}')
    for call in (lambda: so.validate_request(long_state),
                 lambda: so.parse_request(dup_key.encode()),
                 lambda: so.parse_request(b'{"model": NaN}')):
        with pytest.raises(so.SystemOneError) as info:
            call()
        assert MARKER not in str(info.value) and MARKER not in repr(info.value.args)
        assert info.value.__cause__ is None
    assert so.SystemOneError("schema_invalid").args == ("schema_invalid",)


def test_decision_request_mapping_preserves_eligible_set_and_adds_none():
    req = _decision_request(eligible=("hosted", "local"))
    snap = so.from_decision_request(req, "route_choice")
    question = snap["questions"]["route_1"]
    assert list(question["criteria"]) == ["local", "hosted", so.NONE_LABEL]
    assert "skip" not in question["criteria"]
    assert set(so.answer_labels(question)) == set(req["eligible_choice_ids"])
    assert so.read_labels(question, none_option=False)[-1] == so.NONE_LABEL
    options = snap["x_flywheel"]
    assert options["none_option"] is False and options["sensitivity"] == "private"
    assert options["act_on"] == {"route_1": ["local", "hosted"]}
    assert snap["model"] == "auto:route_choice"
    with pytest.raises(so.SystemOneError) as info:
        so.from_decision_request(_decision_request(eligible=()), "route_choice")
    assert info.value.code == "schema_invalid"


@pytest.mark.parametrize("action, mode, choice, expected", [
    ("act", "strict", "local", ("selected", "local")),
    ("abstain", "strict", None, ("abstain", None)),
    ("abstain", "compat", "local", ("abstain", None)),
    ("act", "strict", so.NONE_LABEL, ("abstain", None)),
])
def test_mapping_back_to_decision_contract(action, mode, choice, expected):
    req = _decision_request()
    question = so.from_decision_request(req, "route_choice")["questions"]["route_1"]
    raw = {"local": 0.7, "hosted": 0.2, so.NONE_LABEL: 0.1}
    answer = so.render_answer(question, raw, {"action": action}, mode)
    assert answer["choice"] == ("local" if choice == so.NONE_LABEL else choice)
    answer["choice"] = choice
    proposal = so.to_proposal(answer, {"action": action}, evidence_refs=["ev_roster"])
    result = decision_contract.evaluate_proposal(req, proposal, scorer_ref="readout")
    assert (result["reason_code"], result["choice_id"]) == expected


def _mixed_request(mode: str) -> dict:
    return so.validate_request({
        "model": "m", "state": {"b": 2, "a": 1},
        "questions": {
            "n": {"type": "noul", "instructions": "Is it true?"},
            "c": {"type": "choice", "instructions": "Pick.",
                  "criteria": {"a": "first", "b": "second", "z": "masked"},
                  "x_flywheel": {"eligible": ["a", "b"]}},
            "s": {"type": "score", "instructions": "Rate.", "criteria": ["low", "mid", "high"]}},
        "x_flywheel": {"abstain_mode": mode}})


RAWS = {"n": {"true": 0.18, "false": 0.80, "none": 0.02},
        "c": {"a": 0.6, "b": 0.3, "__none__": 0.1},
        "s": {"0": 0.1, "1": 0.2, "2": 0.6, "__none__": 0.1}}


def _render(mode: str, action: str) -> dict:
    request = _mixed_request(mode)
    return {qid: so.render_answer(q, RAWS[qid], {"action": action}, mode)
            for qid, q in request["questions"].items()}


def test_strict_mode_returns_null_on_abstention():
    answers = _render("strict", "abstain")
    assert answers["n"] == {"type": "noul", "noul": None}
    assert answers["c"]["choice"] is None and answers["s"]["score"] is None
    assert answers["c"]["probabilities"] == {"a": 0.666667, "b": 0.333333}
    assert answers["s"]["legend"] == ["low", "mid", "high"]


def test_compat_mode_keeps_the_argmax_on_abstention():
    answers = _render("compat", "abstain")
    assert answers["n"]["noul"] == 0.183673
    assert answers["c"]["choice"] == "a"
    assert answers["c"]["confidence"] == pytest.approx(0.333333, abs=1e-6)
    assert answers["s"]["score"] == pytest.approx(1.555556, abs=1e-6)
    assert answers["s"]["confidence"] == pytest.approx(0.5, abs=1e-6)
    assert _render("strict", "act") == answers


def test_rendered_answers_validate_and_strict_nulls_are_enforced():
    for mode in ("strict", "compat"):
        request = _mixed_request(mode)
        answers = _render(mode, "abstain")
        decisions = {q: {"action": "abstain", "reason": "below_threshold"} for q in answers}
        body = {"model": "m", "answers": answers, "usage": {"input_tokens": 9,
                "output_tokens": 0}, "x_flywheel": {"decisions": decisions}}
        assert so.validate_response(body, request) == body
    leaked = copy.deepcopy(body)
    leaked["answers"] = _render("compat", "abstain")
    with pytest.raises(so.SystemOneError):
        so.validate_response(leaked, _mixed_request("strict"))
    assert so.render_state(request["state"]) == '{"a": 1, "b": 2}'
    assert so.render_state("plain") == "plain"


def test_eligibility_mask_and_none_only_reads():
    question = _mixed_request("compat")["questions"]["c"]
    assert so.answer_labels(question) == ["a", "b"]
    with pytest.raises(ValueError):
        so.render_answer(question, {"a": 0.5, "z": 0.5}, {"action": "act"}, "compat")
    none_only = so.render_answer(question, {"__none__": 1.0}, {"action": "act"}, "compat")
    assert none_only["choice"] is None and none_only["confidence"] == 0.0
    assert none_only["probabilities"] == {"a": 0.5, "b": 0.5}
