#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Behavior proof for emet/reporters/deepeval.py (the DeepEval reporter).

Constructs FAKE deepeval-shaped result objects - no deepeval install, no model,
no network - and proves the wedge end to end: a completed evaluation becomes a
canonical eval record, the record is sealed into an emet witness receipt, and
`emet check` re-derives RECEIPT_VALID; corrupting one byte flips it to
RECEIPT_TAMPERED; a malformed receipt is RECEIPT_UNVERIFIABLE; and the reporter
handles an absent deepeval import cleanly.

Runs under `python -m pytest -q` AND as a plain `python test_deepeval_reporter.py`
(the conformance CI runs behavior proofs as plain scripts, with no pytest).
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from emet.reporters import deepeval as dr  # noqa: E402
from emet import report, witness_receipt  # noqa: E402

NOW = "2026-07-02T12:34:56Z"


# --- fake deepeval shapes (attribute access, like real deepeval objects) -------
class FakeMetric:
    def __init__(self, name, score, threshold, success, evaluation_model):
        self.name = name
        self.score = score
        self.threshold = threshold
        self.success = success
        self.evaluation_model = evaluation_model


class FakeTestResult:
    def __init__(self, input, success, metrics_data):
        self.input = input
        self.success = success
        self.metrics_data = metrics_data


class FakeEvaluationResult:
    def __init__(self, test_results):
        self.test_results = test_results


def _fake_evaluation():
    return FakeEvaluationResult([
        FakeTestResult(
            input="What is the capital of France?",
            success=True,
            metrics_data=[FakeMetric("AnswerRelevancy", 0.92, 0.7, True, "gpt-4o")],
        ),
        FakeTestResult(
            input="Summarize the second law of thermodynamics.",
            success=False,
            metrics_data=[FakeMetric("Faithfulness", 0.61, 0.8, False, "gpt-4o")],
        ),
    ])


def _record(evaluation=None):
    return dr.build_eval_record(
        evaluation or _fake_evaluation(),
        model="gpt-4o-2024-08-06",
        config={"temperature": "0", "run": "nightly"},
        harness_version="3.6.4",
    )


# --- record shape: provenance, no floats, dataset as a digest ------------------
def test_record_is_deepeval_free_and_float_free():
    record = _record()
    assert record["schema"] == "emet-eval-record/v1"
    assert record["model"] == "gpt-4o-2024-08-06"
    # dataset is a digest + count, never the raw cases.
    assert record["dataset"]["count"] == 2
    assert len(record["dataset"]["digest"]) == 64
    assert record["dataset"]["covers"] == "test_case_inputs"
    assert "What is the capital of France?" not in json.dumps(record)
    # scores/thresholds/pass are strings; no float anywhere in the sealed record.
    def _no_float(obj):
        if isinstance(obj, float):
            return False
        if isinstance(obj, dict):
            return all(_no_float(v) for v in obj.values())
        if isinstance(obj, list):
            return all(_no_float(v) for v in obj)
        return True
    assert _no_float(record), "sealed record must contain no float"
    case0 = record["cases"][0]["metrics"][0]
    assert case0 == {"judge_model": "gpt-4o", "name": "AnswerRelevancy",
                     "passed": "true", "score": "0.92", "threshold": "0.7"}
    assert record["metric"]["names"] == ["AnswerRelevancy", "Faithfulness"]


def test_dataset_digest_is_stable_and_input_sensitive():
    a = _record()["dataset"]["digest"]
    b = _record()["dataset"]["digest"]
    assert a == b  # deterministic
    mutated = _fake_evaluation()
    mutated.test_results[0].input = "a different question"
    assert _record(mutated)["dataset"]["digest"] != a  # binds the inputs


# --- record -> receipt -> check == RECEIPT_VALID -------------------------------
def test_mint_then_check_is_receipt_valid():
    tmp = tempfile.mkdtemp(prefix="emet_dr_")
    receipt, record_path, receipt_path = dr.mint_receipt(
        _fake_evaluation(), model="gpt-4o-2024-08-06",
        config={"temperature": "0"}, out_dir=tmp, now=NOW, harness_version="3.6.4")
    # emet witnesses INTEGRITY only: no eval-quality verdict is asserted.
    assert receipt["verdict_record"] == []
    assert "TRUSTED" not in json.dumps(receipt)
    verdict, _ = witness_receipt.check_receipt(receipt, base_dir=tmp)
    assert verdict == "RECEIPT_VALID"
    # the subject binds the sealed record file's content address.
    with open(record_path, "rb") as fh:
        import hashlib
        assert receipt["subject"][0]["sha256"] == hashlib.sha256(fh.read()).hexdigest()
    # recompute against the real file on disk still re-derives.
    verdict2, _ = witness_receipt.check_receipt(receipt, base_dir=tmp, recompute=True)
    assert verdict2 == "RECEIPT_VALID"
    assert os.path.isfile(receipt_path)


# --- corrupting one byte flips the verdict away from VALID ---------------------
def test_tampered_sealed_field_is_receipt_tampered():
    receipt, _, _ = dr.mint_receipt(
        _fake_evaluation(), model="m", out_dir=tempfile.mkdtemp(prefix="emet_dr_"),
        now=NOW, harness_version="3.6.4")
    sub = receipt["subject"][0]["sha256"]
    receipt["subject"][0]["sha256"] = ("0" if sub[0] != "0" else "1") + sub[1:]
    verdict, _ = witness_receipt.check_receipt(receipt)  # receipt_id untouched
    assert verdict == "RECEIPT_TAMPERED"


def test_tampered_record_bytes_is_receipt_tampered_on_recompute():
    tmp = tempfile.mkdtemp(prefix="emet_dr_")
    receipt, record_path, _ = dr.mint_receipt(
        _fake_evaluation(), model="gpt-4o-2024-08-06", out_dir=tmp, now=NOW,
        harness_version="3.6.4")
    with open(record_path, "ab") as fh:
        fh.write(b"X")  # one extra byte in the sealed record file
    verdict, _ = witness_receipt.check_receipt(receipt, base_dir=tmp, recompute=True)
    assert verdict == "RECEIPT_TAMPERED"


def test_malformed_receipt_is_receipt_unverifiable():
    receipt, _, _ = dr.mint_receipt(
        _fake_evaluation(), model="m", out_dir=tempfile.mkdtemp(prefix="emet_dr_"),
        now=NOW, harness_version="3.6.4")
    receipt.pop("receipt_id")
    verdict, _ = witness_receipt.check_receipt(receipt)
    assert verdict == "RECEIPT_UNVERIFIABLE"


# --- end to end through the real `emet check` CLI ------------------------------
def test_cli_check_receipt_valid_end_to_end():
    tmp = tempfile.mkdtemp(prefix="emet_dr_")
    _, _, receipt_path = dr.mint_receipt(
        _fake_evaluation(), model="gpt-4o-2024-08-06", out_dir=tmp, now=NOW,
        harness_version="3.6.4")
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "membrane.py"), "check", receipt_path],
        capture_output=True, text=True, cwd=tmp)
    assert "RECEIPT_VALID" in proc.stdout
    assert proc.returncode == 0


# --- missing deepeval is handled cleanly ---------------------------------------
def test_missing_deepeval_import_is_clean():
    have_deepeval = importlib.util.find_spec("deepeval") is not None
    if have_deepeval:
        assert dr.require_deepeval().__name__ == "deepeval"
        return
    # deepeval absent: require_deepeval and evaluate_and_mint raise a clear error,
    # never a bare ImportError or traceback from deep inside.
    for call in (lambda: dr.require_deepeval(),
                 lambda: dr.evaluate_and_mint([], [], model="m")):
        try:
            call()
        except RuntimeError as exc:
            assert "deepeval is not installed" in str(exc)
        else:
            raise AssertionError("expected RuntimeError for absent deepeval")


def test_build_record_rejects_empty_model():
    try:
        dr.build_eval_record(_fake_evaluation(), model="")
    except ValueError:
        pass
    else:
        raise AssertionError("empty model must raise ValueError")


def test_accepts_bare_list_of_test_results():
    # a plain list of test-result-shaped objects is a valid evaluation input.
    record = dr.build_eval_record(
        _fake_evaluation().test_results, model="m", harness_version="x")
    assert record["dataset"]["count"] == 2
    assert report.canonical(record)  # canonicalizes without error


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("PASS " + fn.__name__)
    print("OK " + str(len(fns)) + " deepeval-reporter behavior proofs")


if __name__ == "__main__":
    _run_all()
