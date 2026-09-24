"""The experimental chooser must keep request and eligibility boundaries."""
from copy import deepcopy

import pytest

from harness.evidence_json import canonical_sha256


REQUEST = {
    "schema": "flywheel.decision-request/v1", "decision_ref": "fixture:one",
    "state": "Select the available action.",
    "choices": [{"id": "a", "description": "available"},
                {"id": "b", "description": "disabled"}],
    "eligible_choice_ids": ["a"], "evidence_refs": [],
}


class Scorer:
    def __init__(self, *, stale=False, abstain=False, mutate=False):
        self.stale, self.abstain, self.mutate = stale, abstain, mutate

    def score_batch(self, requests, *, task_family):
        request = requests[0]
        envelope = {
            "model_ref": "fixture-model", "task_family": task_family,
            "request_sha256": "0" * 64 if self.stale else canonical_sha256(request),
            "candidate_ids": ["a", "b", "__abstain__"],
            "scores": [
                {"choice_id": "a", "eligible": True, "raw_logit": 1},
                {"choice_id": "b", "eligible": False, "raw_logit": None},
                {"choice_id": "__abstain__", "eligible": True,
                 "raw_logit": 2 if self.abstain else 0},
            ],
        }
        if self.mutate:
            request["state"] = "changed by runtime"
        return [envelope]


def policy(**kwargs):
    from train.classifier_workflow_experiment import ScoredPolicy
    return ScoredPolicy(Scorer(**kwargs))


def test_selects_eligible_action_without_enabling_production_selection():
    chooser = policy()
    assert chooser(deepcopy(REQUEST)) == "a"
    assert chooser.last_score["automatic_selection_enabled"] is False


def test_stale_score_abstains_instead_of_selecting_a_plausible_action():
    chooser = policy(stale=True)
    assert chooser(deepcopy(REQUEST)) is None
    assert chooser.last_status == "scorer_unavailable"


def test_explicit_abstention_is_not_replaced_by_a_forced_choice():
    assert policy(abstain=True)(deepcopy(REQUEST)) is None


def test_runtime_mutation_does_not_change_the_callers_request():
    request = deepcopy(REQUEST)
    assert policy(mutate=True)(request) == "a"
    assert request == REQUEST


def test_impossible_request_blocking_survives_json_key_reordering():
    import json
    from train.classifier_workflow_fixture import Workflow, deterministic_policy, scenarios
    from train.classifier_workflow_outcome import check_outcome

    case = next(c for c in scenarios() if c['id'] == 'missing_destination_blocked')
    # A serializable map's key order cannot determine whether an absent option exists.
    reordered = json.loads(json.dumps(case, sort_keys=True))
    for candidate in (case, reordered):
        env = Workflow(candidate, seed=1709)
        assert deterministic_policy(env.request()) is None
        assert env.step(None)['status'] == 'blocked'
        assert check_outcome(candidate, env.snapshot())['outcome'] == 'blocked'


THREE = {
    "schema": "flywheel.decision-request/v1", "decision_ref": "fixture:three",
    "state": "Select one of three actions.",
    "choices": [{"id": "a", "description": "first"}, {"id": "b", "description": "second"},
                {"id": "c", "description": "third"}],
    "eligible_choice_ids": ["a", "b", "c"], "evidence_refs": [],
}


class Mass:
    """Scores every choice from a fixed map; ids absent from the map get no row."""

    def __init__(self, values, field="probability_like"):
        self.values, self.field = values, field

    def score_batch(self, requests, *, task_family):
        request = requests[0]
        ids = [cid for cid in [c["id"] for c in request["choices"]] + ["__abstain__"]
               if cid in self.values]
        return [{"model_ref": "fixture-model", "task_family": task_family,
                 "request_sha256": canonical_sha256(request), "candidate_ids": ids,
                 "scores": [{"choice_id": cid, "eligible": True, self.field: self.values[cid]}
                            for cid in ids]}]


def chooser_for(values, field="probability_like", **kwargs):
    from train.classifier_workflow_experiment import ScoredPolicy
    return ScoredPolicy(Mass(values, field), **kwargs)


def test_abstain_row_ahead_of_each_candidate_but_under_half_the_mass_acts():
    """The Experiment 002B stall: the old single argmax picked __abstain__ here."""
    values = {"a": .30, "b": .15, "c": .10, "__abstain__": .45}
    assert max(values, key=values.get) == "__abstain__"
    chooser = chooser_for(values)
    assert chooser(deepcopy(THREE)) == "a"
    assert chooser.last_decision == "act"
    assert chooser.last_p_abstain == pytest.approx(.45)


def test_majority_abstain_mass_abstains():
    chooser = chooser_for({"a": .40, "b": .03, "c": .02, "__abstain__": .55})
    assert chooser(deepcopy(THREE)) is None
    assert chooser.last_decision == "abstain"
    assert chooser.last_status == "scored_shadow"


def test_half_the_mass_is_not_a_majority_to_act():
    chooser = chooser_for({"a": .5, "b": 0, "c": 0, "__abstain__": .5})
    assert chooser(deepcopy(THREE)) is None
    assert chooser.last_decision == "abstain"


def test_logits_decide_by_the_joint_softmax():
    # e^1.5 / (e^1 + e^0.9 + e^0.8 + e^1.5) is about 0.377, so the policy acts.
    chooser = chooser_for({"a": 1.0, "b": .9, "c": .8, "__abstain__": 1.5}, "raw_logit")
    assert chooser(deepcopy(THREE)) == "a"
    assert chooser.last_p_abstain == pytest.approx(0.3771, abs=1e-3)


def test_threshold_moves_the_act_or_abstain_line_only():
    values = {"a": .30, "b": .15, "c": .10, "__abstain__": .45}
    assert chooser_for(values, abstain_threshold=.4)(deepcopy(THREE)) is None
    assert chooser_for(values, abstain_threshold=.9)(deepcopy(THREE)) == "a"


@pytest.mark.parametrize("threshold", [0, -.1, 1.5, True, "0.5"])
def test_invalid_threshold_is_refused(threshold):
    with pytest.raises(ValueError):
        chooser_for({"a": 1}, abstain_threshold=threshold)


def test_scorer_without_an_abstain_row_always_acts():
    chooser = chooser_for({"a": -2.0, "b": 3.0, "c": 1.0}, "score")
    assert chooser(deepcopy(THREE)) == "b"
    assert chooser.last_p_abstain == 0


def test_zero_mass_is_incomparable_not_a_choice():
    chooser = chooser_for({"a": 0, "b": 0, "c": 0, "__abstain__": 0})
    assert chooser(deepcopy(THREE)) is None
    assert chooser.last_status == "incomparable_scores"


def test_scorer_exception_type_reaches_the_policy():
    from train.classifier_workflow_experiment import ScoredPolicy

    class Broken:
        def score_batch(self, requests, *, task_family):
            raise MemoryError("device detail")

    chooser = ScoredPolicy(Broken())
    assert chooser(deepcopy(THREE)) is None
    assert (chooser.last_status, chooser.last_error_type) == ("scorer_unavailable", "MemoryError")
