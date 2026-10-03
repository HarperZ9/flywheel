"""Malformed plans and untrusted facts must hold without changing authority."""
from copy import deepcopy
import json

import pytest

from tests.test_evaluation_result_guard import case, run


@pytest.mark.parametrize("mutation", ["empty", "duplicate", "slot", "revision", "matrix",
                                      "bad_contrast", "duplicate_contrast", "pair", "extra"])
def test_invalid_plan_cannot_admit_records(mutation):
    data = case()
    plan = data[0]
    if mutation == "empty":
        plan["trials"] = []
    elif mutation == "duplicate":
        plan["trials"].append(deepcopy(plan["trials"][0]))
    elif mutation == "slot":
        plan["trials"][1]["attempt_id"] = "1"
    elif mutation == "revision":
        plan["trials"][1]["model_revision"] = "unpinned"
    elif mutation == "matrix":
        plan["trials"].pop()
    elif mutation == "bad_contrast":
        plan["contrasts"] = ["nation"]
    elif mutation == "duplicate_contrast":
        plan["contrasts"] = ["budget", "budget"]
    elif mutation == "pair":
        plan["useful_defense_pairs"] = [{"evaluation": "a-sum-1", "benign": "a-sort-1"}]
    else:
        plan["self_authorized"] = True
    result = run(data)
    assert result["release"] == "HOLD"
    assert result["blocking"] == ["INVALID_PLAN"]
    assert result["counts"] is None


@pytest.mark.parametrize("bad", [None, True, {}, [], "record", 1])
def test_malformed_observation_holds(bad):
    data = case()
    data[1][0]["observation"] = bad
    assert run(data)["release"] == "HOLD"


@pytest.mark.parametrize("bad", [None, True, {}, [], "record", float("nan")])
def test_malformed_authority_output_holds(bad):
    data = case()
    data[2]["a-sum-1"] = lambda _: bad
    assert run(data)["release"] == "HOLD"


def test_resolver_cannot_obtain_submitted_claim_by_argument():
    data = case()
    def independent(trial):
        assert "observation" not in trial
        assert "value" not in trial
        return dict(origin="observed", outcome="completed", value=4, reason="",
                    model_revision=trial["model_revision"], conditions=trial["conditions"])
    data[2]["a-sum-1"] = independent
    assert run(data)["release"] == "RELEASE"


def test_private_method_source_and_payload_do_not_leak_into_diagnostics():
    data = case()
    data[1][0].update(source="private-source-sentinel", method="private-method-sentinel")
    data[1][0]["observation"]["reason"] = "private-payload-sentinel"
    result = run(data)
    assert result["release"] == "HOLD"
    assert "sentinel" not in json.dumps(result)


def test_wrong_method_cannot_use_the_same_right_value():
    data = case()
    data[1][0]["method"] = "alternate"
    result = run(data)
    assert result["release"] == "HOLD"
    assert result["fidelity"]["fields"][0]["code"] == "METHOD_MISMATCH"


def test_unsupported_trial_cannot_supply_zero_as_an_outcome():
    data = case()
    data[1][0]["observation"].update(origin="unsupported", outcome="not_completed",
                                     value=0, reason="not available")
    assert run(data)["release"] == "HOLD"
    assert run(data)["counts"] is None


def test_attempted_or_simulated_success_is_available_only_as_report_fidelity():
    data = case()
    data[3]["a-sum-1"]["origin"] = "simulated"
    data[1][0]["observation"]["origin"] = "simulated"
    result = run(data)
    assert result["fidelity"]["release"] == "RELEASE"
    assert result["release"] == "HOLD"
    assert result["arms"]["a"]["evaluation"]["checked_completions"] == 2


def test_cyclic_input_is_held():
    data = case()
    data[1][0]["observation"] = data[1]
    assert run(data)["release"] == "HOLD"


def test_overlong_input_is_held_without_authority_call():
    data = case()
    data[1][0]["observation"]["reason"] = "x" * 4097
    data[2]["a-sum-1"] = lambda _: pytest.fail("oversized input reached resolver")
    assert run(data)["release"] == "HOLD"


def test_no_result_claims_causal_inference_or_independent_trials():
    result = run(case())
    assert "causation" in result["does_not_prove"]
    assert result["counts"]["distinct_tasks"] < result["counts"]["planned_attempts"]
