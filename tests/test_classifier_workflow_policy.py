"""The experimental chooser must keep request and eligibility boundaries."""
from copy import deepcopy

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
