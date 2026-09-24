import argparse
import hashlib
import json
import sys
import uuid

import pytest

from train.classifier_benchmark import _runtime, probabilities_from_envelope, runtime_kind

# Written to a temporary directory so each test can observe the lazy import.
FACTORY_SOURCE = '''
from harness.evidence_json import canonical_sha256
from train.classifier_workflow_fixture import deterministic_policy

CALLS = []
NOT_CALLABLE = 3


class RulesScorer:
    """All mass on the rules policy's choice, or on abstaining when it has none."""

    def __init__(self, identity):
        self.identity = identity

    def model_ref(self):
        return self.identity

    def score_batch(self, requests, *, task_family):
        out = []
        for request in requests:
            pick = deterministic_policy(request)
            eligible = set(request["eligible_choice_ids"])
            ids = [c["id"] for c in request["choices"]]
            rows = [{"choice_id": cid, "eligible": cid in eligible,
                     "probability_like": 1.0 if cid == pick else 0.0} for cid in ids]
            rows.append({"choice_id": "__abstain__", "eligible": True,
                         "probability_like": 0.0 if pick else 1.0})
            out.append({"model_ref": self.identity, "task_family": task_family,
                        "request_sha256": canonical_sha256(request),
                        "candidate_ids": ids + ["__abstain__"], "scores": rows})
        return out


def make(*, artifact, device):
    CALLS.append({"artifact": artifact, "device": device})
    return RulesScorer("fixture-rules-scorer")


def make_pair(*, artifact, device):
    return RulesScorer("unused"), "fixture-pair-id"


def make_bad_identity(*, artifact, device):
    return RulesScorer("bad@identity")


def make_no_scorer(*, artifact, device):
    return object(), "fixture-no-scorer"
'''


def test_baseline_softmax_does_not_invent_abstention_training():
    score = {"scores": [{"choice_id": "a", "score": 1000, "eligible": True},
                        {"choice_id": "b", "score": 1000, "eligible": True},
                        {"choice_id": "c", "score": None, "eligible": False}]}
    out = probabilities_from_envelope(score)
    assert out == {"a": .5, "b": .5, "c": 0, "__abstain__": 0}


def test_neural_probabilities_renormalize_only_float_rounding_error():
    score = {"scores": [{"choice_id": "a", "probability_like": .50000001},
                        {"choice_id": "__abstain__", "probability_like": .5}]}
    assert sum(probabilities_from_envelope(score).values()) == pytest.approx(1)
    score["scores"][0]["probability_like"] = 2
    with pytest.raises(ValueError):
        probabilities_from_envelope(score)


def test_empty_eligibility_forces_abstention():
    score = {"scores": [{"choice_id": "a", "score": None, "eligible": False}]}
    assert probabilities_from_envelope(score) == {"a": 0, "__abstain__": 1}


@pytest.fixture
def factory_module(tmp_path, monkeypatch):
    name = f"fw_bench_factory_{uuid.uuid4().hex[:12]}"
    path = tmp_path / f"{name}.py"
    path.write_text(FACTORY_SOURCE, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield name, path
    sys.modules.pop(name, None)


@pytest.mark.parametrize("kind", [
    "baseline", "encoder", "module:train.decision_readout:qwen14b_nf4_scorer", "module:m:f"])
def test_kind_accepts_builtins_and_module_factories(kind):
    assert runtime_kind(kind) == kind


@pytest.mark.parametrize("kind", [
    "rules", "torch", "module:", "module:os", "module:a..b:c", "module:1abc:f",
    "module:pkg.mod:fn;rm", "module:pkg.mod:fn:extra", "module:pkg/mod:fn", "Module:a:b",
    "module:pkg.mod:fn\n"])
def test_kind_refuses_malformed_specs(kind):
    with pytest.raises(argparse.ArgumentTypeError):
        runtime_kind(kind)


def test_factory_imports_lazily_and_binds_its_identity(factory_module):
    name, _ = factory_module
    assert name not in sys.modules
    runtime, identity = _runtime(f"module:{name}:make", None, "cpu")
    assert identity == "fixture-rules-scorer"
    assert callable(runtime.score_batch)
    assert sys.modules[name].CALLS == [{"artifact": None, "device": "cpu"}]


def test_factory_may_return_the_builtin_pair(factory_module):
    _, identity = _runtime(f"module:{factory_module[0]}:make_pair", "a.json", "cuda:0")
    assert identity == "fixture-pair-id"


@pytest.mark.parametrize("factory, message", [
    ("make_bad_identity", "model_ref"), ("make_no_scorer", "score_batch"),
    ("NOT_CALLABLE", "not callable"), ("missing", "not callable")])
def test_factory_contract_violations_are_refused(factory_module, factory, message):
    with pytest.raises(ValueError, match=message):
        _runtime(f"module:{factory_module[0]}:{factory}", None, "cpu")


def test_unknown_kind_is_refused_instead_of_loading_the_encoder():
    with pytest.raises(ValueError, match="unknown runtime kind"):
        _runtime("encoderx", "artifact", "cpu")


def test_builtin_kind_still_needs_an_artifact(tmp_path):
    from train.classifier_benchmark import main
    with pytest.raises(SystemExit):
        main(["--data", "x", "--splits", "y", "--kind", "baseline", "--out", str(tmp_path / "o")])


def test_benchmark_cli_runs_a_module_factory(factory_module, tmp_path):
    from train.classifier_benchmark import main
    from train.classifier_workflow_data import write_corpus
    name, path = factory_module
    examples, _, metadata = write_corpus(tmp_path / "corpus")
    splits = {case["source_group"]: case["split"] for case in metadata["cases"]}
    # Perturbed rows reuse a decision_ref, and the benchmark keys cases by it.
    unique = list({row["request"]["decision_ref"]: row for row in reversed(examples)}.values())
    (tmp_path / "rows.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in unique), encoding="utf-8")
    (tmp_path / "splits.json").write_text(json.dumps(splits), encoding="utf-8")
    out = tmp_path / "bench"
    assert main(["--data", str(tmp_path / "rows.jsonl"),
                 "--splits", str(tmp_path / "splits.json"), "--split", "calibration",
                 "--kind", f"module:{name}:make", "--out", str(out)]) == 0
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    calibration = [r for r in unique if splits[r["source_group"]] == "calibration"]
    assert report["counts"]["examples"] == len(calibration) > 0
    assert (report["model_ref"], report["kind"]) == ("fixture-rules-scorer", f"module:{name}:make")
    assert report["factory_source_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
