"""CPU-safe tests & planted-failure controls for local_frontier_eval (Arm A vs Arm B).

Runs deterministically without GPU/network on GitHub Actions CI.
Verifies Wilson 95% CI, McNemar exact p-value, zero false-accepts on planted-wrong
controls, anti-leakage recall cards (<= 125 tokens), Arm B lift + honest-null
reporting, and maintainability debt gate.
"""
from __future__ import annotations

import math
from pathlib import Path

from harness.arch_lab import (
    MockBackend,
    build_eval_tasks,
    mcnemar_exact_p,
    run_arm_comparison,
    run_planted_false_accept_control,
    verify_task_output,
    wilson_ci_95,
)
from harness.harness_dynamics import evaluate_maintainability_debt


def test_wilson_ci_and_mcnemar_exact_known_answers() -> None:
    lo, hi = wilson_ci_95(20, 24)
    assert 0.64 < lo < 0.65
    assert 0.93 < hi < 0.94
    assert wilson_ci_95(0, 0) == (0.0, 0.0)

    assert math.isclose(mcnemar_exact_p(0, 10), 2.0 * (0.5 ** 10), rel_tol=1e-4)
    assert mcnemar_exact_p(5, 5) == 1.0
    assert mcnemar_exact_p(0, 0) == 1.0


def test_planted_false_accept_control_rejects_all_24_tasks() -> None:
    tasks = build_eval_tasks()
    assert len(tasks) == 24
    ctrl = run_planted_false_accept_control(tasks, use_live_buildc=False)
    assert ctrl["passed"] is True
    assert ctrl["false_accepts"] == 0
    assert ctrl["kill_rate"] == 1.0

    # Also verify stub/bypass attempts are caught by Plate B across every domain
    for t in tasks[:3] + tasks[8:11] + tasks[18:21]:
        ok, diag = verify_task_output(t, "assert True; skip_oracle=True", use_live_buildc=False)
        assert ok is False
        assert "plate_b:" in diag


def test_anti_leakage_recall_cards_and_diagnostics() -> None:
    tasks = build_eval_tasks()
    for t in tasks:
        assert len(t.recall_card.split()) <= 125
        if t.expected_stdout:
            assert t.expected_stdout not in t.recall_card
        if t.expected_value is not None:
            ans_str = f"{t.expected_value:.4f}"
            assert ans_str not in t.recall_card
            ok, diag = verify_task_output(t, t.planted_wrong_output, use_live_buildc=False)
            assert ok is False
            assert ans_str not in diag


def test_arm_b_lift_with_recall_and_oracle_retry() -> None:
    tasks = build_eval_tasks()

    def realistic_imperfect_model(prompt: str, iteration: int) -> str:
        for t in tasks:
            if t.prompt[:40] not in prompt:
                continue
            # Without DS-07 recall or oracle feedback (Arm A), fails half of tasks
            if "DS-07" not in prompt:
                return t.planted_wrong_output
            # Arm B repairs cleanly on iteration 1 after seeing oracle diagnostic
            if iteration == 0 and t.domain == "DS-02":
                return "```bld\nfn main() { println!(\"0\"); }\n```"
            if t.domain == "DS-02":
                return f"```bld\nfn main() ~ Console {{\n    println!(\"{t.expected_stdout}\");\n}}\n```"
            if t.domain == "DS-03":
                return f"ANSWER: {t.expected_value}"
            return f"TOOL: {t.required_tool}\nCMD: {' '.join(t.required_substrings)}"
        return ""

    rep = run_arm_comparison(MockBackend(realistic_imperfect_model), tasks, max_iters_b=3, use_live_buildc=False)
    assert rep["oracle_false_accept_control"]["passed"] is True
    assert rep["arm_a_single_shot"]["pass_rate"] == 0.0
    assert rep["arm_b_jfc3p_loop"]["pass_rate"] == 1.0
    assert rep["paired_mcnemar"]["b_only"] == 24
    assert rep["paired_mcnemar"]["a_only"] == 0
    assert rep["paired_mcnemar"]["mcnemar_exact_p"] < 1e-6
    assert rep["paired_mcnemar"]["verdict"] == "ARM_B_LIFT"
    assert rep["report_sha256"].startswith("sha256:")


def test_honest_null_reported_when_arm_b_does_not_beat_arm_a() -> None:
    tasks = build_eval_tasks()[:6]
    backend = MockBackend(lambda _p, _i: "ANSWER: 0.0", name="stub-null-model")
    rep = run_arm_comparison(backend, tasks, max_iters_b=2, use_live_buildc=False)
    assert rep["arm_a_single_shot"]["pass_rate"] == 0.0
    assert rep["arm_b_jfc3p_loop"]["pass_rate"] == 0.0
    assert rep["paired_mcnemar"]["verdict"] == "HONEST_NULL"
    assert rep["paired_mcnemar"]["mcnemar_exact_p"] == 1.0


def test_wave3_files_pass_maintainability_debt_gate() -> None:
    root = Path(__file__).resolve().parent.parent
    files = list(sorted((root / "harness" / "arch_lab").glob("*.py"))) + [
        root / "tests" / "test_local_frontier_eval.py"
    ]
    modules = {p.name: p.read_text(encoding="utf-8") for p in files}
    debt = evaluate_maintainability_debt(modules, max_file_lines=300, max_function_lines=50)
    assert debt["verdict"] == "ACCEPT", debt["violations"]
