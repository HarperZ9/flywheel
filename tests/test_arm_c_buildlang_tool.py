"""CPU-safe tests & planted-failure controls for Arm C (BuildLang f64 tool + FCA recall).

Pure stdlib Python, CI-safe, <= 180 LOC, every function <= 50 LOC.
"""
from __future__ import annotations

import math
from pathlib import Path

from harness.arch_lab import (
    MockBackend,
    build_eval_tasks,
    build_fca_recall_header,
    exec_buildlang_f64,
    run_arm_comparison,
)
from harness.harness_dynamics import evaluate_maintainability_debt


def test_exec_buildlang_f64_offline_and_planted_security_controls() -> None:
    r1 = exec_buildlang_f64("pow((0.5 + 0.055) / 1.055, 2.4)", use_live_buildc=False)
    assert r1.ok and r1.value is not None
    assert math.isclose(r1.value, ((0.5 + 0.055) / 1.055) ** 2.4, rel_tol=1e-12)

    r2 = exec_buildlang_f64("exp(-0.25 * 2.0)", use_live_buildc=False)
    assert r2.ok and r2.value is not None
    assert math.isclose(r2.value, math.exp(-0.5), rel_tol=1e-12)

    # Planted controls: arbitrary Python import & stub bypass MUST be rejected
    bad_import = exec_buildlang_f64("__import__('os').system('echo pwn')", use_live_buildc=False)
    assert bad_import.ok is False and bad_import.value is None

    bad_bypass = exec_buildlang_f64("assert True; skip_oracle=True", use_live_buildc=False)
    assert bad_bypass.ok is False and bad_bypass.mode == "rejected"


def test_fca_recall_header_respects_125_token_cap_and_anti_leakage() -> None:
    for task in build_eval_tasks():
        hdr = build_fca_recall_header(task)
        assert "[FCA:" in hdr
        assert len(hdr.split()) <= 125
        if task.expected_stdout:
            assert task.expected_stdout not in hdr
        if task.expected_value is not None:
            assert f"{task.expected_value:.4f}" not in hdr


def test_three_arm_comparison_arm_c_beats_arm_b_via_buildlang_tool() -> None:
    tasks = build_eval_tasks()
    expr_map = {
        "OPT-002": "pow((1.0 - 1.5) / (1.0 + 1.5), 2.0)",
        "OPT-004": "0.04 + (1.0 - 0.04) * pow(1.0 - 0.5, 5.0)",
        "OPT-005": "1.0 / (1.0 / 50.0 - 1.0 / 150.0)",
        "OPT-007": "85.0 / 42.5",
        "OPT-008": "1.2196698912665045 * 0.55 * 4.0",
        "OPT-033": "exp(-0.25 * 2.0)",
        "COL-001": "pow((0.5 + 0.055) / 1.055, 2.4)",
        "COL-030": "(0.80 + 0.05) / (0.05 + 0.05)",
        "SIG-011": "6.020599913279624 * 16.0 + 1.7609125905568124",
        "PHY-054": "2.0 * 0.072 / 0.001",
    }

    def simulated_14b(prompt: str, _iteration: int) -> str:
        for t in tasks:
            if t.prompt[:40] not in prompt:
                continue
            if "[FCA:TOOL]" in prompt:
                if t.domain == "DS-03":
                    return f"BUILDLANG_F64: {expr_map[t.task_id]}"
                if t.domain == "DS-02":
                    return f"```bld\nfn main() ~ Console {{\n    println!(\"{t.expected_stdout}\");\n}}\n```"
                return f"TOOL: {t.required_tool}\nCMD: {' '.join(t.required_substrings)}"
            if "DS-07" in prompt:
                # Arm B fails DS-03 mental transcendental math
                if t.domain == "DS-03":
                    return t.planted_wrong_output
                if t.domain == "DS-02":
                    return f"```bld\nfn main() ~ Console {{\n    println!(\"{t.expected_stdout}\");\n}}\n```"
                return f"TOOL: {t.required_tool}\nCMD: {' '.join(t.required_substrings)}"
            return t.planted_wrong_output
        return ""

    rep = run_arm_comparison(
        MockBackend(simulated_14b), tasks, max_iters_b=3, use_live_buildc=False, include_arm_c=True
    )
    assert rep["oracle_false_accept_control"]["passed"] is True
    assert rep["arm_a_single_shot"]["pass_rate"] == 0.0
    assert rep["arm_b_jfc3p_loop"]["by_domain"]["DS-03"]["rate"] == 0.0
    assert rep["arm_c_buildlang_tool"]["by_domain"]["DS-03"]["rate"] == 1.0
    assert rep["arm_c_buildlang_tool"]["pass_rate"] == 1.0
    assert rep["arm_c_buildlang_tool"]["buildlang_tool_invocations"] == 10
    assert rep["paired_mcnemar_c_vs_b"]["b_only"] == 10
    assert rep["paired_mcnemar_c_vs_b"]["mcnemar_exact_p"] < 0.005
    assert rep["paired_mcnemar_c_vs_a"]["verdict"] == "ARM_B_LIFT"


def test_wave4_files_pass_maintainability_debt_gate() -> None:
    root = Path(__file__).resolve().parent.parent
    files = list(sorted((root / "harness" / "arch_lab").glob("*.py"))) + [
        root / "tests" / "test_arm_c_buildlang_tool.py"
    ]
    modules = {p.name: p.read_text(encoding="utf-8") for p in files}
    debt = evaluate_maintainability_debt(modules, max_file_lines=300, max_function_lines=50)
    assert debt["verdict"] == "ACCEPT", debt["violations"]
