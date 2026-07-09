"""Falsifiers for the guarded Hugging Face publisher.

Load-bearing property: the command CANNOT reach READY_TO_UPLOAD unless every
gate is green, and the benchmark gate specifically blocks on an inconclusive
outside-observer result unless the operator acknowledges the honest null.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.publish_to_huggingface import evaluate_gates, _benchmark_gate


READINESS = {"models": [{"model": "14B", "trained_artifact_present": True,
                         "verdict": "MODEL_RELEASE_READY_STATIC",
                         "root": "E:/release/flywheel-local-coder-14b"}]}
STAGE = {"models": [{"model": "14B", "repo_id": "HarperZ9/flywheel-local-coder-14b",
                     "upload_status": "WAITING_FOR_OPERATOR_UPLOAD_APPROVAL"}]}
CI_NULL = {"hard.json": {"difference": {"point": 0.1, "ci_95": [-0.24, 0.42],
                                        "includes_zero": True, "method": "newcombe"}}}
CI_REAL = {"hard.json": {"difference": {"point": 0.3, "ci_95": [0.12, 0.48],
                                        "includes_zero": False, "method": "paired_bootstrap"}}}


def _eval(**kw):
    base = dict(model="14B", readiness=READINESS, stage=STAGE, ci=CI_NULL,
                token_present=True, operator_approved=True, acknowledge_null=False)
    base.update(kw)
    return evaluate_gates(**base)


def test_all_green_only_with_real_effect_or_acknowledged_null():
    assert _eval(ci=CI_REAL)["decision"] == "READY_TO_UPLOAD"
    assert _eval(ci=CI_NULL, acknowledge_null=True)["decision"] == "READY_TO_UPLOAD"


def test_inconclusive_benchmark_blocks_by_default():
    r = _eval(ci=CI_NULL, acknowledge_null=False)
    assert r["decision"] == "BLOCKED"
    assert any(g["gate"] == "benchmark_outside_observer" and not g["passed"] for g in r["gates"])


def test_no_token_blocks():
    r = _eval(ci=CI_REAL, token_present=False)
    assert r["decision"] == "BLOCKED"
    assert any(g["gate"] == "hf_token_present" and not g["passed"] for g in r["gates"])


def test_no_operator_approval_blocks():
    r = _eval(ci=CI_REAL, operator_approved=False)
    assert r["decision"] == "BLOCKED"


def test_untrained_track_blocks():
    readiness = {"models": [{"model": "32B", "trained_artifact_present": False,
                             "verdict": "MODEL_NO_TRAINED_ARTIFACT"}]}
    stage = {"models": [{"model": "32B", "repo_id": "HarperZ9/flywheel-local-coder-32b",
                         "upload_status": "DO_NOT_UPLOAD"}]}
    r = evaluate_gates(model="32B", readiness=readiness, stage=stage, ci=CI_REAL,
                       token_present=True, operator_approved=True, acknowledge_null=True)
    assert r["decision"] == "BLOCKED"
    assert any(g["gate"] == "trained_artifact_present" and not g["passed"] for g in r["gates"])
    assert any(g["gate"] == "stage_not_blocked" and not g["passed"] for g in r["gates"])


def test_benchmark_gate_reason_names_the_instrument():
    g = _benchmark_gate(CI_NULL, acknowledge_null=False)
    assert not g["passed"]
    assert "100-task" in g["reason"]


def test_real_effect_reads_excludes_zero():
    g = _benchmark_gate(CI_REAL, acknowledge_null=False)
    assert g["passed"] and g["excludes_zero"]
