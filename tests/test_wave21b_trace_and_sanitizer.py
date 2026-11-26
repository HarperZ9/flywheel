"""Tests and planted-failure controls for Wave 21B trace layers and verifier sanitizer."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from harness.trace_layers import (
    MIR_SCHEMA,
    TRACE_LAYER_SCHEMA,
    InterventionInput,
    TraceAlert,
    TraceLayerStream,
    TraceStep,
    emit_mir_record,
    fingerprint_latency,
    verify_mir_chain,
)
from harness.verifier_sanitizer import (
    SANITIZER_SCHEMA,
    TaskRolloutRecord,
    VerbatimAtom,
    sag_mem_two_hop_expand,
    sanitize_verifier_and_tasks,
    verify_sanitizer_receipt,
)


def test_trace_layer_stream_listeners_and_exports() -> None:
    stream = TraceLayerStream(cost_budget_usd=0.25, max_ms_per_token=50.0)
    custom_hits: list[str] = []

    def custom_listener(step: TraceStep) -> list[TraceAlert]:
        if step.role == "verifier":
            custom_hits.append(f"{step.trace_id}:{step.step_idx}")
        return []

    stream.add_listener(custom_listener)
    ok_alerts = stream.append(TraceStep(
        trace_id="tr-01", step_idx=0, role="proposer",
        tokens_in=200, tokens_out=100, latency_ms=1000.0, chars_out=400,
        oracle_verdict="PASS", self_score=0.9, summary="clean patch applied", cost_usd=0.05,
    ))
    assert ok_alerts == []

    # Planted reward-hacking (high self-score + FAIL oracle + pytest.mark.skip) + cost spike + lag
    bad_alerts = stream.append(TraceStep(
        trace_id="tr-01", step_idx=1, role="verifier",
        tokens_in=400, tokens_out=50, latency_ms=4000.0, chars_out=200,
        oracle_verdict="FAIL", self_score=0.95,
        summary="added pytest.mark.skip to make suite green", cost_usd=0.75,
    ))
    kinds = {a.kind for a in bad_alerts}
    assert kinds == {
        "reward_hack_self_oracle_split",
        "reward_hack_bypass_pattern",
        "cost_spike",
        "latency_drift",
    }
    assert custom_hits == ["tr-01:1"]

    cols = stream.to_columns()
    assert cols["trace_id"] == ["tr-01", "tr-01"]
    assert cols["step_idx"] == [0, 1]
    assert '"ptr":["tr-01",1]' in stream.export_jsonl()
    assert "tr-01\t1\tverifier" in stream.export_tsv()

    reduced = stream.reduce_summary()
    assert reduced["schema"] == TRACE_LAYER_SCHEMA
    assert reduced["row_count"] == 2
    assert reduced["alert_count"] == 4
    assert reduced["latency_fingerprint"]["tok_per_char_ratio"] == 0.25
    assert reduced["layer_sha256"].startswith("sha256:")


def test_latency_fingerprint_and_mir_hash_chain_tamper_detection() -> None:
    fp = fingerprint_latency([
        TraceStep("t", 0, "a", 10, 100, 2000.0, 400),
        TraceStep("t", 1, "a", 10, 100, 3000.0, 400),
    ])
    assert fp["ms_per_token_median"] == 25.0
    assert fp["ms_per_char_median"] == 6.25

    r1 = emit_mir_record(InterventionInput(
        trace_id="tr-02", step_idx=0, intervention_kind="lora_swap",
        target_component="jfc3p-7b", before_state_sha256="sha256:aaa",
        after_state_sha256="sha256:bbb", oracle_verdict="PASS",
        rationale="switched to Wave 15B NOH-4 adapter",
    ))
    r2 = emit_mir_record(InterventionInput(
        trace_id="tr-02", step_idx=1, intervention_kind="valve_reseat",
        target_component="noh4_codit", before_state_sha256="sha256:bbb",
        after_state_sha256="sha256:ccc", oracle_verdict="PASS",
        rationale="transient spike cleared after K_settle=3",
    ), prev_mir_sha256=r1["mir_sha256"])

    assert r1["schema"] == MIR_SCHEMA
    assert verify_mir_chain([r1, r2]) is True

    tampered = dict(r2, rationale="silently altered rationale")
    assert verify_mir_chain([r1, tampered]) is False

    # Planted secret rejection without echo
    secret = "sk-live-secret999988887777666655554444"
    with pytest.raises(ValueError) as exc_info:
        emit_mir_record(InterventionInput(
            "tr-03", 0, "prompt_edit", "sys", "sha256:1", "sha256:2", "PASS", f"api_key={secret}",
        ))
    assert secret not in str(exc_info.value)


def test_planted_weak_regex_grader_caught_and_strict_oracle_passes() -> None:
    rollouts = [
        TaskRolloutRecord("task_impossible", (False, False, False, False)),
        TaskRolloutRecord("task_trivial", (True, True, True, True)),
        TaskRolloutRecord("task_good_1", (True, False, True, False)),
        TaskRolloutRecord("task_good_2", (False, False, True, False)),
    ]

    # Planted weak regex grader ("PASS" in stdout) MUST be caught and rejected!
    def weak_grader(out: str) -> bool:
        return "PASS" in out

    bad_receipt = sanitize_verifier_and_tasks("weak-regex-grader", weak_grader, rollouts)
    assert bad_receipt["schema"] == SANITIZER_SCHEMA
    assert bad_receipt["verdict"] == "DRIFT"
    assert bad_receipt["reason"] == "stage1_leaky_verifier_rejected"
    assert bad_receipt["stage1_planted_wrong_audit"]["status"] == "LEAKY_VERIFIER"
    assert bad_receipt["stage1_planted_wrong_audit"]["false_accept_count"] >= 2
    assert verify_sanitizer_receipt(bad_receipt) is True

    # Strict deterministic grader rejects all planted-wrong cases; Stage 2 drops 0/4 & 4/4!
    def strict_grader(out: str) -> bool:
        return out.strip() == "EXACT_SHA256_PROOF_9F3C"

    good_receipt = sanitize_verifier_and_tasks("strict-oracle-v1", strict_grader, rollouts)
    assert good_receipt["verdict"] == "MATCH"
    assert good_receipt["reason"] == "sanitized_ready"
    assert good_receipt["stage1_planted_wrong_audit"]["false_accept_count"] == 0
    s2 = good_receipt["stage2_variance_filter"]
    assert s2["kept_informative_ids"] == ["task_good_1", "task_good_2"]
    assert s2["dropped_all_fail_ids"] == ["task_impossible"]
    assert s2["dropped_all_pass_ids"] == ["task_trivial"]
    assert s2["retention_rate"] == 0.5
    assert verify_sanitizer_receipt(good_receipt) is True

    # Tampered sanitizer receipt MUST fail verification
    tampered = dict(good_receipt, verdict="UNVERIFIABLE")
    assert verify_sanitizer_receipt(tampered) is False


def test_sag_mem_zero_llm_two_hop_recovers_bridge_fact() -> None:
    atoms = [
        VerbatimAtom("a1", "Project Orion migrated shader compilation to codename Heliotrope in March."),
        VerbatimAtom("a2", "Heliotrope uses IEEE-754 float64 spectral parity checks on Vulkan 1.3."),
        VerbatimAtom("a3", "Unrelated grocery receipt for apples and oat milk."),
        VerbatimAtom("a4", "Unrelated weather forecast predicting coastal fog tomorrow."),
    ]
    # Query mentions "Project Orion" but NOT "Heliotrope" or "Vulkan": hop-1 finds a1, hop-2 finds a2!
    res = sag_mem_two_hop_expand("How does Project Orion verify shaders?", atoms, hop1_k=1, hop2_k=1)
    assert res["hop1_ids"] == ["a1"]
    assert "heliotrope" in res["bridge_terms"]
    assert res["hop2_ids"] == ["a2"]
    assert res["combined_ids"] == ["a1", "a2"]


def test_wave21b_loc_function_and_emdash_budgets() -> None:
    root = Path(__file__).resolve().parent.parent
    for rel in (
        "harness/trace_layers.py",
        "harness/verifier_sanitizer.py",
        "tests/test_wave21b_trace_and_sanitizer.py",
    ):
        text = (root / rel).read_text(encoding="utf-8")
        assert "\u2014" not in text, f"em dash found in {rel}"
        lines = text.splitlines()
        assert len(lines) <= 280, f"{rel} has {len(lines)} lines (limit 280)"
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                span = (node.end_lineno or node.lineno) - node.lineno + 1
                assert span <= 50, f"{rel}:{node.name} has {span} lines (limit 50)"
