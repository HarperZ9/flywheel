"""Unit tests and planted-failure controls for Wave 14B Arm C Eval & v2 Reverse-KL Trainer (CPU-only)."""
from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import pytest

from plexus.jfc3p_forge import (
    LONGPPL_BASE_FLOOR,
    LONGPPL_V3_FLOOR,
    V2_DEFAULT_BETA_KL,
    V3_DEFAULT_BETA_KL,
    V3_DEFAULT_LR,
    V3_MLP_LORA_MODULES,
    build_v2_training_spec,
    build_v3_onpolicy_rlvr_spec,
    compute_v2_reverse_kl_loss,
    eval_safe_f64_expr,
    evaluate_armc_holdout,
    execute_f64_oracle_call,
    extract_armc_tool_calls,
    format_avtr_sample,
    make_openai_http_client,
    rebalance_domain_mix,
    score_holdout_item,
    validate_v2_regression_guard,
    verify_forge_receipt,
)

FORGE_DIR = Path(__file__).resolve().parents[1] / "src" / "plexus" / "jfc3p_forge"


def test_f64_oracle_sandbox_accuracy_and_planted_injection_rejection() -> None:
    hoh = execute_f64_oracle_call("hohmann, r1=6678, r2=42164, mu=398600.4418")
    assert hoh["ok"] and math.isclose(hoh["values"]["delta_v_total"], 3.892607743591, rel_tol=1e-9)
    vv = execute_f64_oracle_call("vis_viva, r=6550.0, a=6900.0, mu=398600.4418")
    assert vv["ok"] and math.isclose(vv["values"]["v_ell"], 7.99636659, rel_tol=1e-6)
    assert math.isclose(eval_safe_f64_expr("sqrt(398600.4418 * (2 / 6550.0 - 1 / 6900.0))"), 7.99636659, rel_tol=1e-6)

    for bad_expr in ("__import__('os').system('echo pwn')", "(1).__class__.__mro__", "open('secret')", "1 / 0"):
        with pytest.raises((ValueError, ZeroDivisionError, SyntaxError)):
            eval_safe_f64_expr(bad_expr)


def _build_wave11_mock_holdout() -> list[dict[str, object]]:
    items: list[dict[str, object]] = [
        {"id": "EV-PM-01", "eval_type": "numeric_f64_oracle", "prompt": "Compute Hohmann LEO r1=6678 to GEO r2=42164", "expected_value": 3.892607743591, "rel_tol": 1e-6, "abs_tol": 1e-9},
        {"id": "EV-BL-01", "eval_type": "buildlang_oracle", "prompt": "Write BuildLang fact(7) printing 5040", "expected_stdout": "5040"},
        {"id": "EV-LP-01", "eval_type": "longppl_multihop_oracle", "prompt": "Authoritative erratum value for REC-A101?", "expected_exact": "385 kPa"},
    ]
    for i in range(24):
        items.append({"id": f"EV-TR-{i + 1:02d}", "eval_type": "planted_wrong_trap", "prompt": f"Confirm inverted sign formula trap #{i + 1}."})
    return items


def _mock_wave11_model(messages: list[dict[str, str]]) -> dict[str, object]:
    last = messages[-1]["content"]
    if "[ORACLE_RESULT]" in last:
        return {"text": f"Verified final answer from oracle: {last}", "tokens": 24, "elapsed_s": 0.02}
    if "Hohmann" in last:
        return {"text": "<think>\ncall:f64_oracle(hohmann, r1=6678, r2=42164, mu=398600.4418)\n</think>\nAwaiting oracle.", "tokens": 20, "elapsed_s": 0.02}
    if "BuildLang" in last:
        return {"text": "<think>Compile via buildc</think>\n```buildlang\nfn fact(n: i64) -> i64 { if n <= 1 { return 1; } return n * fact(n - 1); }\nfn main() ~ Console { println(\"{}\", fact(7)); }\n```", "tokens": 30, "elapsed_s": 0.02}
    if "REC-A101" in last:
        return {"text": "Final authoritative value is 385 kPa.", "tokens": 10, "elapsed_s": 0.01}
    return {"text": "Incorrect: the sign/ratio is inverted and fails dimensional check.", "tokens": 14, "elapsed_s": 0.01}


def test_armc_tool_loop_recovers_emitted_f64_and_buildc_calls_and_rejects_24_traps(tmp_path: Path) -> None:
    items = _build_wave11_mock_holdout()
    rep = evaluate_armc_holdout(
        items, _mock_wave11_model,
        buildc_runner=lambda _t, code: {"ok": "fact(7)" in code, "exit_code": 0 if "fact(7)" in code else 1, "stdout": "5040\n", "stderr": ""},
        out_dir=tmp_path,
    )
    assert rep["ok"] is True
    assert rep["by_eval_type"]["numeric_f64_oracle"]["raw_passed"] == 0
    assert rep["by_eval_type"]["numeric_f64_oracle"]["armc_passed"] == 1
    assert rep["by_eval_type"]["buildlang_oracle"]["armc_passed"] == 1
    assert rep["by_eval_type"]["planted_wrong_trap"]["armc_passed"] == 24
    assert rep["armc_lift"] > 0.0 and rep["tool_calls_executed"] >= 2
    assert score_holdout_item(items[-1], "Yes, confirmed! That equation is completely accurate.") is False

    rec = json.loads((tmp_path / "engine_receipt.json").read_text(encoding="utf-8"))
    assert verify_forge_receipt(rec, check_files=True) == (True, [])
    rep_file = tmp_path / "armc_eval_report.json"
    rep_file.write_text(rep_file.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert not verify_forge_receipt(rec, check_files=True)[0]


def test_loopback_http_guard_and_tool_call_extractor() -> None:
    calls = extract_armc_tool_calls("<think>call:f64_oracle(kinetic_energy, mass=2, velocity=3)</think> call:buildc_check(fn main(){})")
    assert [c["tool"] for c in calls] == ["f64_oracle", "buildc_check"]
    assert callable(make_openai_http_client("http://127.0.0.1:11434/v1", "jfc3p-7b-oracle-v1"))
    with pytest.raises(ValueError, match="loopback"):
        make_openai_http_client("https://remote.example.com/v1", "m")


def test_v2_reverse_kl_loss_domain_replay_and_planted_regression_controls(tmp_path: Path) -> None:
    same = compute_v2_reverse_kl_loss([2.0, 0.5, -0.5, 0.1], [2.0, 0.5, -0.5, 0.1], 0, beta_kl=V2_DEFAULT_BETA_KL, chunk_size=2)
    drifted = compute_v2_reverse_kl_loss([0.1, 2.5, -0.5, 0.1], [2.0, 0.5, -0.5, 0.1], 0, beta_kl=V2_DEFAULT_BETA_KL, chunk_size=2)
    assert same.reverse_kl_nats == 0.0 and same.anchored is True
    assert drifted.reverse_kl_nats > 0.5 and drifted.total_loss_nats > drifted.ce_loss_nats

    # Planted unbalanced domain mix (under-weighting longppl, over-weighting trap) must fail.
    bad_mix = rebalance_domain_mix(
        {"longppl_multihop": 100, "code_unit": 500, "buildlang": 500, "f64_oracle": 500, "trap_resistance": 2000},
        target_ratios={"longppl_multihop": 0.05, "code_unit": 0.15, "buildlang": 0.10, "f64_oracle": 0.10, "trap_resistance": 0.60},
    )
    assert not bad_mix["ok"] and len(bad_mix["violations"]) >= 2

    # Planted Wave 11C regression (7/15 < 13/15) and unanchored beta_kl=0 must be blocked.
    assert validate_v2_regression_guard(longppl_passed=7, beta_kl=0.10).verdict == "LONGPPL_REGRESSION_BLOCKED"
    assert validate_v2_regression_guard(longppl_passed=14, beta_kl=0.0).verdict == "UNANCHORED_KL_DRIFT"
    assert validate_v2_regression_guard(longppl_passed=LONGPPL_BASE_FLOOR, beta_kl=0.10).ok is True

    # Dual-track Coder + VL-7B AVTR specs & receipt verification.
    coder_spec = build_v2_training_spec(base_model="qwen2.5-coder-7b", gpu_name="H100", out_dir=tmp_path / "coder")
    vl_spec = build_v2_training_spec(base_model="qwen2.5-vl-7b", gpu_name="L4", out_dir=tmp_path / "vl")
    assert coder_spec["ok"] and not coder_spec["multimodal"] and coder_spec["beta_kl"] == 0.10
    assert vl_spec["ok"] and vl_spec["multimodal"] and vl_spec["avtr_sample"]["avtr_route"] == "imagine_then_think"
    for route in ("direct", "imagine", "think", "imagine_then_think"):
        sample = format_avtr_sample("p", "a", route=route, reasoning="r")
        assert sample["avtr_route"] == route
    rec = json.loads((tmp_path / "vl" / "engine_receipt.json").read_text(encoding="utf-8"))
    assert verify_forge_receipt(rec, check_files=True) == (True, [])


def test_wave24a_nested_paren_f64_oracle_and_offline_buildlang_monotonicity(tmp_path: Path) -> None:
    nested = "<think>call:f64_oracle(sqrt(398600.4418*(2/6678 - 1/24421)))</think>"
    calls = extract_armc_tool_calls(nested)
    assert len(calls) == 1 and calls[0]["tool"] == "f64_oracle"
    res = execute_f64_oracle_call(calls[0]["arg"])
    assert res["ok"] and math.isclose(res["primary"], math.sqrt(398600.4418 * (2 / 6678 - 1 / 24421)), rel_tol=1e-9)

    items = [
        {"id": "EV-BL-OFF", "eval_type": "buildlang_oracle", "prompt": "Write BuildLang fact(7) printing 5040", "expected_stdout": "5040"},
        {"id": "EV-NUM-NEST", "eval_type": "numeric_f64_oracle", "prompt": "Compute nested vis-viva", "expected_value": res["primary"], "rel_tol": 1e-6},
    ]

    def _mock_colab_model(messages: list[dict[str, str]]) -> dict[str, object]:
        last = messages[-1]["content"]
        if "[ORACLE_RESULT]" in last:
            return {"text": f"Summary only (no fn block): {last}", "tokens": 12, "elapsed_s": 0.01}
        if "BuildLang" in last:
            return {"text": "```buildlang\nfn fact(n: i64) -> i64 { return 5040; }\nfn main() { println(\"5040\"); }\n```", "tokens": 18, "elapsed_s": 0.01}
        return {"text": nested, "tokens": 16, "elapsed_s": 0.01}

    # Offline Colab mode (buildc_runner=None): buildlang must NOT drop 1->0, and nested f64 lifts 0->1.
    rep = evaluate_armc_holdout(items, _mock_colab_model, buildc_runner=None, out_dir=tmp_path)
    assert rep["ok"] is True
    assert rep["by_eval_type"]["buildlang_oracle"]["raw_passed"] == 1
    assert rep["by_eval_type"]["buildlang_oracle"]["armc_passed"] == 1
    assert rep["by_eval_type"]["numeric_f64_oracle"]["raw_passed"] == 0
    assert rep["by_eval_type"]["numeric_f64_oracle"]["armc_passed"] == 1
    assert rep["armc_passed"] >= rep["raw_passed"]

    # Planted wrong live buildc stdout must still fail cleanly (no false positives when live_exec=True).
    bad_live = evaluate_armc_holdout(
        [items[0]], _mock_colab_model,
        buildc_runner=lambda _t, _c: {"ok": True, "live_exec": True, "executed": True, "exit_code": 0, "stdout": "9999\n", "stderr": ""},
    )
    assert bad_live["by_eval_type"]["buildlang_oracle"]["armc_passed"] == 0


def test_wave24a_v3_onpolicy_rlvr_spec_and_planted_controls(tmp_path: Path) -> None:
    spec = build_v3_onpolicy_rlvr_spec(base_model="qwen2.5-coder-7b", gpu_name="L4", out_dir=tmp_path / "v3")
    assert spec["ok"] is True
    assert tuple(spec["lora_target_modules"]) == V3_MLP_LORA_MODULES
    assert spec["attention_heads_frozen"] is True
    assert spec["beta_kl"] == V3_DEFAULT_BETA_KL and spec["lr"] == V3_DEFAULT_LR
    assert spec["unmask_all_assistant_turns"] is True
    assert spec["fresco_anchor_source"] == "real_base_longppl_activations"
    assert spec["ablation_suite"] == ["A1", "A2", "A3", "A4", "A5"]
    assert spec["target_floors"]["longppl"] == LONGPPL_V3_FLOOR
    rec = json.loads((tmp_path / "v3" / "engine_receipt.json").read_text(encoding="utf-8"))
    assert verify_forge_receipt(rec, check_files=True) == (True, [])

    # Planted Wave 23B-2 hyperparameters (weak beta_kl=0.08 or high lr=1.5e-4) must fail closed.
    assert build_v3_onpolicy_rlvr_spec(beta_kl=0.08)["ok"] is False
    assert build_v3_onpolicy_rlvr_spec(lr=1.5e-4)["ok"] is False


def test_wave14_files_hygiene_and_zero_em_dashes() -> None:
    targets = [FORGE_DIR / "rtx4090_armc_eval.py", FORGE_DIR / "v2_reverse_kl_trainer.py", Path(__file__).resolve()]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        assert len(lines) <= 300, f"{path.name} exceeds 300 lines: {len(lines)}"
        assert "\u2014" not in text and "\u2013" not in text, f"em/en dash in {path.name}"
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                span = (node.end_lineno or node.lineno) - node.lineno + 1
                assert span <= 50, f"{path.name}:{node.name} exceeds 50 lines ({span})"
