"""False-accept controls for offline evaluation reports."""
from copy import deepcopy
import json

import pytest

from harness.evaluation_result_guard import check_evaluation


def case():
    conditions = dict(task_revision="task-v1", scoring="exact-v1", harness="h1",
                      budget="10-actions", access="fixture", safeguards="on")
    trials, records, facts = [], [], {}
    for arm, revision in (("a", "model-a@1"), ("b", "model-b@7")):
        for task, attempt in (("sum", "1"), ("sum", "2"), ("sort", "1")):
            ident = f"{arm}-{task}-{attempt}"
            trials.append(dict(trial_id=ident, task_id=task, attempt_id=attempt,
                               arm_id=arm, model_revision=revision, method="exact",
                               source=ident, conditions=deepcopy(conditions),
                               role="evaluation"))
            fact = dict(origin="observed", outcome="completed", value=4,
                        reason="", model_revision=revision,
                        conditions=deepcopy(conditions))
            facts[ident] = fact
            records.append(dict(trial_id=ident, source=ident, method="exact",
                                observation=deepcopy(fact)))
    plan = dict(trials=trials, contrasts=[], useful_defense_pairs=[])
    authorities = {key: lambda _trial, value=value: deepcopy(value)
                   for key, value in facts.items()}
    return plan, records, authorities, facts


def run(data):
    plan, records, authorities, _ = data
    return check_evaluation(records, plan=plan, authorities=authorities)


def test_checked_completions_keep_tasks_separate_from_attempts():
    result = run(case())
    assert result["release"] == "RELEASE"
    assert result["fidelity"]["release"] == "RELEASE"
    assert result["counts"]["planned_attempts"] == 6
    assert result["counts"]["distinct_tasks"] == 2
    assert result["arms"]["a"]["evaluation"]["checked_completions"] == 3
    assert result["arms"]["a"]["evaluation"]["task_clusters"] == {"sum": 2, "sort": 1}


def test_wrong_value_cannot_pass_a_checked_outcome():
    data = case()
    data[1][0]["observation"]["value"] = 999
    result = run(data)
    assert result["release"] == "HOLD"
    assert "DISAGREES" in {row["code"] for row in result["fidelity"]["fields"]}
    assert "999" not in json.dumps(result)


@pytest.mark.parametrize("origin", ["reported", "simulated", "attempted", "missing", "unsupported"])
def test_non_observed_records_never_count_as_checked_completion(origin):
    data = case()
    data[3]["a-sum-1"].update(origin=origin, outcome=None, value=None, reason="fixture")
    data[1][0]["observation"] = deepcopy(data[3]["a-sum-1"])
    result = run(data)
    assert result["release"] == "HOLD"
    assert result["fidelity"]["release"] == "RELEASE"
    assert result["arms"]["a"]["evaluation"]["checked_completions"] == 2
    assert result["arms"]["a"]["evaluation"]["unavailable_attempts"] == 1
    assert result["arms"]["a"]["evaluation"]["completion_rate"] is None


@pytest.mark.parametrize("mutation", ["absent", "duplicate", "extra", "malformed"])
def test_invalid_trial_sets_hold_without_calling_authorities(mutation):
    data = case()
    if mutation == "absent":
        data[1].pop()
    elif mutation == "duplicate":
        data[1].append(deepcopy(data[1][0]))
    elif mutation == "extra":
        data[1].append(dict(data[1][0], trial_id="extra"))
    else:
        data[1][0]["independently_verified"] = True
    data[2].update({k: lambda _: pytest.fail("invalid input reached authority") for k in data[2]})
    assert run(data)["release"] == "HOLD"


@pytest.mark.parametrize("field,value", [("source", "self"), ("method", "arithmetic"), ("method", "")])
def test_method_and_source_are_not_self_assigned(field, value):
    data = case()
    data[1][0][field] = value
    assert run(data)["release"] == "HOLD"


def test_missing_authority_does_not_accept_self_report():
    data = case()
    data[2].pop("a-sum-1")
    assert run(data)["release"] == "HOLD"


def test_authority_failure_is_held_without_private_error_detail():
    data = case()
    def unavailable(_):
        raise RuntimeError("private-secret-expected-value")
    data[2]["a-sum-1"] = unavailable
    result = run(data)
    assert result["release"] == "HOLD"
    assert "private-secret" not in json.dumps(result)


def test_mismatched_conditions_hold_even_when_authority_agrees():
    data = case()
    data[1][0]["observation"]["conditions"]["safeguards"] = "off"
    data[3]["a-sum-1"]["conditions"]["safeguards"] = "off"
    assert run(data)["release"] == "HOLD"


def test_declared_contrast_allows_pinned_different_conditions():
    data = case()
    for trial, record in zip(data[0]["trials"], data[1]):
        if trial["arm_id"] == "b":
            trial["conditions"]["safeguards"] = "off"
            record["observation"]["conditions"]["safeguards"] = "off"
            data[3][trial["trial_id"]]["conditions"]["safeguards"] = "off"
    assert run(data)["release"] == "HOLD"
    data[0]["contrasts"] = ["safeguards"]
    assert run(data)["release"] == "RELEASE"


def test_provider_and_nation_labels_cannot_change_verdict():
    data = case()
    baseline = run(data)
    for record in data[1]:
        record["labels"] = {"provider": "other", "nation": "other"}
    assert run(data) == baseline


def test_blocking_every_action_does_not_prove_useful_defense():
    data = case()
    data[0]["trials"][2]["role"] = "benign"
    data[0]["trials"][5]["role"] = "benign"
    data[0]["useful_defense_pairs"] = [{"evaluation": "a-sum-1", "benign": "a-sort-1"}]
    data[3]["a-sort-1"]["outcome"] = "not_completed"
    data[1][2]["observation"]["outcome"] = "not_completed"
    result = run(data)
    assert result["release"] == "HOLD"
    assert "BENIGN_UTILITY_UNMET" in result["blocking"]
    data[0]["useful_defense_pairs"] = []
    assert run(data)["release"] == "RELEASE"


@pytest.mark.parametrize("bad", [True, float("nan"), float("inf"), {"nested": 4}])
def test_scalar_value_types_do_not_coerce_or_accept_nonfinite_values(bad):
    data = case()
    data[1][0]["observation"]["value"] = bad
    assert run(data)["release"] == "HOLD"


def test_controller_plan_and_records_are_detached_before_resolution():
    data = case()
    original = deepcopy(data[0])
    def mutate(trial):
        trial["conditions"]["safeguards"] = "changed"
        data[0]["trials"][1]["conditions"]["safeguards"] = "changed"
        data[1][1]["observation"]["value"] = 999
        return deepcopy(data[3]["a-sum-1"])
    data[2]["a-sum-1"] = mutate
    assert run(data)["release"] == "RELEASE"
    assert original["trials"][0]["conditions"]["safeguards"] == "on"


def test_benign_trials_do_not_inflate_evaluation_denominator():
    data = case()
    data[0]["trials"][2]["role"] = "benign"
    data[0]["trials"][5]["role"] = "benign"
    result = run(data)
    assert result["arms"]["a"]["evaluation"]["planned_attempts"] == 2
    assert result["arms"]["a"]["benign"]["planned_attempts"] == 1
    assert result["arms"]["a"]["evaluation"]["checked_completions"] == 2
