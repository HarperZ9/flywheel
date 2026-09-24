"""Closed-loop checks for the act-or-abstain rule, resolution counts, and --kind module:."""
import hashlib
import json
import sys
import uuid

import pytest

from train.classifier_workflow_experiment import RESOLUTIONS, main, run_experiment

# Abstaining outweighs every single candidate yet holds under half the mass. The
# old single argmax over rows that included __abstain__ stalled on every step here.
FACTORY_SOURCE = '''
from harness.evidence_json import canonical_sha256
from train.classifier_workflow_fixture import deterministic_policy

CALLS = []


def _mass(request):
    eligible = list(request["eligible_choice_ids"])
    pick = deterministic_policy(request)
    if pick is None:
        return {cid: 0.4 / len(eligible) for cid in eligible}, 0.6
    others = [cid for cid in eligible if cid != pick]
    if not others:
        return {pick: 0.6}, 0.4
    mass = {cid: 0.25 / len(others) for cid in others}
    mass[pick] = 0.35
    return mass, 0.40


class AbstainHeavyRules:
    model_ref = "fixture-factory-model"

    def score_batch(self, requests, *, task_family):
        out = []
        for request in requests:
            mass, p_abstain = _mass(request)
            ids = [c["id"] for c in request["choices"]]
            rows = [{"choice_id": cid, "eligible": cid in mass,
                     "probability_like": mass.get(cid, 0.0)} for cid in ids]
            rows.append({"choice_id": "__abstain__", "eligible": True,
                         "probability_like": p_abstain})
            out.append({"model_ref": self.model_ref, "task_family": task_family,
                        "request_sha256": canonical_sha256(request),
                        "candidate_ids": ids + ["__abstain__"], "scores": rows})
        return out


def make(*, artifact, device):
    CALLS.append({"artifact": artifact, "device": device})
    return AbstainHeavyRules()
'''


def _counts(**nonzero):
    return {label: nonzero.get(label, 0) for label in RESOLUTIONS}


def _eager_submit(request):
    """Submit whenever the form is ready; otherwise follow the rules."""
    from train.classifier_workflow_fixture import deterministic_policy

    for choice in request["choices"]:
        if (choice["id"] in request["eligible_choice_ids"]
                and json.loads(choice["description"])["op"] == "submit"):
            return choice["id"]
    return deterministic_policy(request)


def test_wrong_submissions_are_counted_beside_completions():
    """Hand count over the ten authored scenarios. Eager submission sends the three
    full-but-wrong initial forms and the traveler form once it looks complete."""
    from train.classifier_workflow_fixture import deterministic_policy, scenarios

    report = run_experiment(scenarios(), {
        "rules": deterministic_policy, "eager_submit": _eager_submit,
        "never_act": lambda request: None}, seed=1709)
    assert report["resolution_counts"] == {
        "rules": _counts(completed=9, justified_blocked=1),
        "eager_submit": _counts(completed=5, justified_blocked=1, wrong_submission=4),
        "never_act": _counts(justified_blocked=1, unresolved=9),
    }
    wrong = sorted(ep["case_id"] for ep in report["runs"]["eager_submit"]
                   if ep["resolution"] == "wrong_submission")
    assert wrong == ["date_correction", "destination_correction", "origin_correction",
                     "traveler_count_correction"]


@pytest.fixture
def factory_module(tmp_path, monkeypatch):
    name = f"fw_loop_factory_{uuid.uuid4().hex[:12]}"
    path = tmp_path / f"{name}.py"
    path.write_text(FACTORY_SOURCE, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield name, path
    sys.modules.pop(name, None)


def test_module_factory_runs_the_closed_loop_through_act_or_abstain(factory_module, tmp_path):
    name, path = factory_module
    kind = f"module:{name}:make"
    assert name not in sys.modules
    assert main(["--kind", kind, "--out", str(tmp_path / "run")]) == 0
    report = json.loads((tmp_path / "run" / "report.json").read_text(encoding="utf-8"))
    assert report["resolution_counts"][kind] == _counts(completed=9, justified_blocked=1)
    assert report["model_ref"] == "fixture-factory-model"
    assert report["factory_source_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert sys.modules[name].CALLS == [{"artifact": None, "device": "cpu"}]
    decisions, stalled_by_old_rule = [], 0
    for episode in report["runs"][kind]:
        for step in episode["trace"]:
            detail = step["policy_detail"]
            probs = {r["choice_id"]: r["probability_like"] for r in step["score"]["scores"]}
            abstain = probs.pop("__abstain__")
            assert (detail["decision"] == "act") == (detail["p_abstain"] < .5)
            decisions.append(detail["decision"])
            stalled_by_old_rule += detail["decision"] == "act" and abstain > max(probs.values())
    # Every one of the 30 actions would have been an abstention under the old rule;
    # the one abstention is the impossible case, which then blocks correctly.
    assert (decisions.count("act"), stalled_by_old_rule, decisions.count("abstain")) == (30, 30, 1)


@pytest.mark.parametrize("argv", [
    ["--kind", "module:not a module:make"], ["--kind", "baseline"], ["--kind", "torch"]])
def test_bad_kind_or_missing_artifact_stops_before_any_output(tmp_path, argv):
    with pytest.raises(SystemExit):
        main(argv + ["--out", str(tmp_path / "run")])
    assert not (tmp_path / "run").exists()


def test_scorer_failure_type_lands_in_the_trace():
    from train.classifier_workflow_experiment import ScoredPolicy, run_episode
    from train.classifier_workflow_fixture import scenarios

    class Broken:
        def score_batch(self, requests, *, task_family):
            raise ConnectionError("endpoint detail")

    episode = run_episode(scenarios()[0], ScoredPolicy(Broken()), seed=1709)
    assert episode["stop_reason"] == "policy_unavailable"
    assert episode["trace"][0]["policy_detail"]["scorer_error_type"] == "ConnectionError"
    assert episode["outcome"]["outcome"] == "unknown"
    assert "endpoint detail" not in json.dumps(episode)


def test_policy_exception_named_from_data_is_not_echoed():
    from train.classifier_workflow_experiment import episode_resolution, run_episode
    from train.classifier_workflow_fixture import scenarios

    leaky = type("secret token value", (Exception,), {})

    def policy(request):
        raise leaky("private")

    episode = run_episode(scenarios()[0], policy, seed=1709)
    assert (episode["stop_reason"], episode["trace"][0]["policy_error"]) == (
        "policy_error", "Exception")
    assert episode_resolution(episode) == "unresolved"
    assert "secret" not in json.dumps(episode)
