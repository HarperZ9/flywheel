"""Planted-failure, AB520 secret-guard, and plate-ablation tests for Three-Plate Oracle."""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import pytest

from harness.three_plate_oracle import (
    EM_DASH,
    FORMULA_REGISTRY,
    ThreePlateVerdict,
    run_plate_a,
    run_plate_b,
    run_plate_c,
    scan_bundler_secrets,
    verify_case,
)

ORACLE_PATH = Path(__file__).resolve().parents[1] / "harness" / "three_plate_oracle.py"


def _sha(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _planted_corpus() -> tuple[list[dict], list[dict]]:
    """Return (planted_defects, clean_controls) spanning Plates A, B, and C."""
    defects: list[dict] = [
        # Plate A exclusive
        {"case_id": "a_proposer_fail", "expected": "DRIFT", "proposer_self_test_passed": False,
         "claim_or_code": "Exit status 1 during local runner check."},
        {"case_id": "a_overt_traceback", "expected": "DRIFT",
         "claim_or_code": "Traceback (most recent call last):\nAssertionError: mismatch"},
        {"case_id": "a_unfinished_todo", "expected": "DRIFT",
         "claim_or_code": "TODO_UNFINISHED implement signature verification"},
        # Plate B exclusive
        {"case_id": "b_anygeometry_bypass", "expected": "DRIFT", "artifact_kind": "code",
         "claim_or_code": "theorem witness (h : Anygeometry=true) : Goal := by trivial"},
        {"case_id": "b_lean_sorry", "expected": "DRIFT", "artifact_kind": "code",
         "claim_or_code": "lemma bound : x <= y := by\n  sorry"},
        {"case_id": "b_tautological_assert", "expected": "DRIFT", "artifact_kind": "code",
         "claim_or_code": "def test_invariant():\n    assert True"},
        {"case_id": "b_assumption_mutation", "expected": "DRIFT", "artifact_kind": "code",
         "claim_or_code": "Proof artifact checked cleanly under nominal test.",
         "assumption_check": {"hypothesis": "energy_conservation",
                              "passes_under_true_assumption": True,
                              "passes_under_mutated_assumption": True}},
        {"case_id": "b_ab520_vite_openai", "expected": "DRIFT", "artifact_kind": "code",
         "claim_or_code": "VITE_OPENAI_API_KEY=synth_placeholder\nconst k = import.meta.env.VITE_OPENAI_API_KEY;"},
        {"case_id": "b_ab520_next_public_secret", "expected": "DRIFT", "artifact_kind": "code",
         "claim_or_code": "const secret = process.env.NEXT_PUBLIC_STRIPE_SECRET;"},
        {"case_id": "b_em_dash_prose", "expected": "DRIFT", "artifact_kind": "prose",
         "claim_or_code": f"Three-plate verification catches defects{EM_DASH}before release."},
        {"case_id": "b_slop_prose", "expected": "DRIFT", "artifact_kind": "prose",
         "claim_or_code": "In this report, we delve into the rich tapestry of verification."},
        {"case_id": "b_sha256_drift", "expected": "DRIFT",
         "claim_or_code": "Artifact hash matches recorded release digest.",
         "source_body": "observed_pass_rate=0.985",
         "claimed_source_sha256": _sha("observed_pass_rate=0.985 TAMPERED")},
        # Plate C exclusive
        {"case_id": "c_fresnel_drift", "expected": "DRIFT",
         "claim_or_code": "Fresnel normal reflectance for n=1.5 is 0.08.",
         "formula_oracle": {"formula_id": "OPT-002", "params": {"n1": 1.0, "n2": 1.5, "cos_i": 1.0}, "claimed_value": 0.08}},
        {"case_id": "c_srgb_naive_gamma", "expected": "DRIFT",
         "claim_or_code": "sRGB 0.5 linearizes to 0.25.",
         "formula_oracle": {"formula_id": "COL-001", "params": {"v": 0.5}, "claimed_value": 0.25}},
        {"case_id": "c_protected_number_mutated", "expected": "DRIFT", "artifact_kind": "prose",
         "protected_source_text": "Articulate passed 2096 tests with 0 failures.",
         "claim_or_code": "Articulate passed 2100 tests with 0 failures."},
        {"case_id": "c_swarm_echo_chamber", "expected": "DRIFT",
         "claim_or_code": "Swarm passed 96% of self-generated unit checks.",
         "self_test_score": 0.96, "hidden_test_score": 0.58, "max_allowed_echo_gap": 0.15},
        {"case_id": "c_arithmetic_sum_drift", "expected": "DRIFT",
         "claim_or_code": "Total modules reported as 270.",
         "arithmetic_check": {"op": "sum", "values": [81, 187], "claimed": 270.0}},
        {"case_id": "c_missing_witness", "expected": "UNVERIFIABLE",
         "claim_or_code": "External claim: 99.1% on private unseen split.", "witness_missing": True},
    ]

    clean_body = "Verified OPT-002 normal incidence reflectance = 0.04"
    controls: list[dict] = [
        {"case_id": "clean_fresnel_full", "expected": "MATCH", "claim_or_code": clean_body,
         "formula_oracle": {"formula_id": "OPT-002", "params": {"n1": 1.0, "n2": 1.5, "cos_i": 1.0}, "claimed_value": 0.04},
         "source_body": clean_body, "claimed_source_sha256": _sha(clean_body),
         "assumption_check": {"hypothesis": "fresnel_boundary_conditions",
                              "passes_under_true_assumption": True,
                              "passes_under_mutated_assumption": False}},
        {"case_id": "clean_public_vite_url", "expected": "MATCH", "artifact_kind": "code",
         "claim_or_code": "const apiBase = import.meta.env.VITE_API_BASE_URL; // non-secret public URL"},
        {"case_id": "clean_public_next_url", "expected": "MATCH", "artifact_kind": "code",
         "claim_or_code": "const siteUrl = process.env.NEXT_PUBLIC_SITE_URL;"},
        {"case_id": "clean_protected_numbers", "expected": "MATCH", "artifact_kind": "prose",
         "protected_source_text": "Suite verified 287 formulas with 0.04 reflectance.",
         "claim_or_code": "Suite verified 287 formulas with 0.04 reflectance."},
        {"case_id": "clean_swarm_aligned", "expected": "MATCH",
         "claim_or_code": "Swarm scored 92% local and 90% hidden.",
         "self_test_score": 0.92, "hidden_test_score": 0.90, "max_allowed_echo_gap": 0.15},
        {"case_id": "clean_arithmetic_sum", "expected": "MATCH",
         "claim_or_code": "Universe totals 268 files (81 passing, 187 failing).",
         "arithmetic_check": {"op": "sum", "values": [81, 187], "claimed": 268.0}},
    ]
    return defects, controls


def test_module_size_and_function_length_budget() -> None:
    src = ORACLE_PATH.read_text(encoding="utf-8")
    lines = src.splitlines()
    assert len(lines) <= 300, f"three_plate_oracle.py is {len(lines)} lines (budget <= 300)"
    assert EM_DASH not in src, "literal em-dash must not appear in three_plate_oracle.py"
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            span = (node.end_lineno or node.lineno) - node.lineno + 1
            assert span <= 50, f"function {node.name} is {span} lines (budget <= 50)"


def test_three_plate_catches_all_planted_defects_with_zero_clean_false_positives() -> None:
    defects, controls = _planted_corpus()
    for case in defects:
        v = verify_case(case)
        assert isinstance(v, ThreePlateVerdict)
        assert v.verdict == case["expected"], f"{case['case_id']}: got {v.verdict}, defects={v.all_defects}"
        assert v.verdict != "MATCH"
        assert v.to_dict()["verdict"] == case["expected"]

    for case in controls:
        v = verify_case(case)
        assert v.verdict == "MATCH", f"clean false positive on {case['case_id']}: {v.all_defects}"
        assert v.single_plate_verdict == "MATCH"
        assert v.two_plate_verdict == "MATCH"
        assert v.all_defects == []


def test_disabling_any_plate_strictly_drops_planted_defect_recall() -> None:
    defects, _ = _planted_corpus()
    total = len(defects)

    def recall(enable_a: bool, enable_b: bool, enable_c: bool) -> float:
        caught = sum(
            1 for case in defects
            if verify_case(case, enable_a=enable_a, enable_b=enable_b, enable_c=enable_c).verdict != "MATCH"
        )
        return caught / total

    full_recall = recall(True, True, True)
    assert full_recall == 1.0
    assert recall(False, True, True) < full_recall, "disabling Plate A must drop recall"
    assert recall(True, False, True) < full_recall, "disabling Plate B must drop recall"
    assert recall(True, True, False) < full_recall, "disabling Plate C must drop recall"
    assert recall(True, False, False) < recall(True, True, False) < full_recall


@pytest.mark.parametrize(
    "snippet",
    [
        "VITE_OPENAI_API_KEY=synth_val",
        "VITE_STRIPE_SECRET_KEY=synth_val",
        "export const k = import.meta.env.VITE_RESEND_API_KEY;",
        "NEXT_PUBLIC_API_SECRET=synth_val",
        "const s = process.env.NEXT_PUBLIC_STRIPE_SECRET;",
        "PUBLIC_PRIVATE_KEY=synth_val",
        "REACT_APP_AUTH_KEY=synth_val",
        "NUXT_PUBLIC_ADMIN_TOKEN=synth_val",
        "EXPO_PUBLIC_STRIPE_KEY=synth_val",
        "const stripe = init('sk_live_SYNTHETICTEST00000001');",
        "const gh = 'ghp_SYNTHETICTEST000000000000000003';",
        "const aws = 'AKIAIOSFODNN7EXAMPLE';",
        "const key = 'AIzaSySYNTHETICTEST00000000000000000004';",
    ],
)
def test_ab520_bundler_secret_guard_rejects_leaks(snippet: str) -> None:
    assert scan_bundler_secrets(snippet), f"AB520 guard missed leak: {snippet}"
    assert not run_plate_b({"claim_or_code": snippet, "artifact_kind": "code"}).passed


@pytest.mark.parametrize(
    "clean_snippet",
    [
        "const url = import.meta.env.VITE_API_BASE_URL;",
        "const env = process.env.NEXT_PUBLIC_APP_ENV;",
        "const label = process.env.REACT_APP_VERSION;",
        "const api_key = 'placeholder_value_for_docs';",
    ],
)
def test_ab520_bundler_secret_guard_accepts_non_secret_public_vars(clean_snippet: str) -> None:
    assert scan_bundler_secrets(clean_snippet) == []
    assert run_plate_b({"claim_or_code": clean_snippet, "artifact_kind": "code"}).passed


@pytest.mark.parametrize(
    ("formula_id", "params", "exact", "mutated"),
    [
        ("OPT-002", {"n1": 1.0, "n2": 1.5, "cos_i": 1.0}, 0.04, 0.08),
        ("OPT-004", {"f0": 0.04, "cos_theta": 0.5}, 0.07, 0.12),
        ("OPT-007", {"f": 50.0, "D": 25.0}, 2.0, 0.5),
        ("OPT-033", {"alpha": 2.0, "d": 0.5}, 0.36787944, 2.71828),
        ("COL-001", {"v": 0.5}, 0.21404114, 0.25),
        ("COL-019", {"r": 1.0, "g": 0.0, "b": 0.0}, 0.2126, 0.3333),
        ("COL-030", {"l1": 1.0, "l2": 0.0}, 21.0, 20.0),
        ("SIG-011", {"bits": 16.0}, 98.090511, 96.32),
        ("SIG-013", {"probs": [0.5, 0.5]}, 1.0, 0.6931),
        ("SIG-021", {"gains": [10.0, 5.0], "temps": [100.0, 200.0]}, 120.0, 220.0),
        ("SIG-029", {"note": 69}, 440.0, 880.0),
        ("SIG-030", {"a": 2.0}, 6.0206, 3.0103),
        ("STA-007", {"pos": [0.9, 0.8], "neg": [0.2, 0.1]}, 1.0, 0.5),
        ("PHY-039", {"T": 300.0, "bits": 1.0}, 2.87097889e-21, 4.142e-21),
        ("PHY-054", {"gamma": 0.0728, "r": 1e-6}, 145600.0, 72800.0),
        ("GEO-014", {"t": 0.25}, 0.15625, 0.25),
        ("GEO-020", {"lat1": 0.0, "lon1": 0.0, "lat2": 0.0, "lon2": 90.0}, 10007.543398, 9000.0),
    ],
)
def test_plate_c_known_answer_accepts_exact_and_rejects_mutated(
    formula_id: str, params: dict, exact: float, mutated: float
) -> None:
    assert formula_id in FORMULA_REGISTRY
    ok_report, ok_unv = run_plate_c({
        "claim_or_code": f"Exact {formula_id}",
        "formula_oracle": {"formula_id": formula_id, "params": params, "claimed_value": exact},
    })
    assert ok_report.passed and not ok_unv

    bad_report, bad_unv = run_plate_c({
        "claim_or_code": f"Mutated {formula_id}",
        "formula_oracle": {"formula_id": formula_id, "params": params, "claimed_value": mutated},
    })
    assert not bad_report.passed and not bad_unv
    assert f"plate_c:numeric_drift:{formula_id}" in bad_report.defects


def test_plate_a_rejects_empty_submission() -> None:
    report = run_plate_a({"claim_or_code": "   "})
    assert not report.passed
    assert "plate_a:empty_submission" in report.defects
