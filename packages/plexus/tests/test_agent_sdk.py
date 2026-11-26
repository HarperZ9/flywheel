"""Known-answer and planted-failure tests for the cross-flagship FlagshipAgentSDK."""
from __future__ import annotations

import ast
import copy
from pathlib import Path

from plexus import (
    BUILTIN_SDK_TOOLS,
    AuthorityContext,
    ColabJobRequest,
    FlagshipAgentSDK,
    emit_colab_job_spec,
    export_compact_catalog,
    verify_workflow_trace,
)

SRC_DIR = Path(__file__).resolve().parents[1] / "src" / "plexus"
SDK_FILES = ("sdk_catalog.py", "sdk_colab.py", "agent_sdk.py")


def test_sdk_module_size_function_budgets_and_hygiene():
    for name in SDK_FILES:
        path = SRC_DIR / name
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        assert len(lines) <= 280, f"{name} exceeded 280 LOC: {len(lines)}"
        assert "\u2014" not in text, f"em dash found in {name}"
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                span = (node.end_lineno or node.lineno) - node.lineno + 1
                assert span <= 50, f"{name}:{node.name} exceeded 50 lines ({span})"


def test_compact_catalog_token_budget_and_formats():
    assert len(BUILTIN_SDK_TOOLS) == 12
    for fmt in ("compact", "openai", "mcp"):
        cat = export_compact_catalog(max_tokens_per_tool=125, fmt=fmt)
        assert cat["tool_count"] == 12
        for tool_name, toks in cat["token_estimates"].items():
            assert toks <= 125, f"{fmt}:{tool_name} exceeded 125 tokens ({toks})"
    sdk = FlagshipAgentSDK()
    names = {t["name"] for t in sdk.catalog()["tools"]}
    expected = {
        "cmmns.ingest_sidecar", "gather.deconstruct", "superframe.synthesize_material",
        "superframe.forge_meshlet_glb", "superframe.step_physai", "superframe.run_noh1",
        "buildlang.compile_and_check", "buildlang.eval_kernel", "flywheel.verify_three_plate",
        "flywheel.run_operator_plan", "colab.emit_stage1_job_spec", "site.verify_surface",
    }
    assert names == expected


def test_multi_flagship_chained_workflow_and_hash_chain_verification(tmp_path):
    sdk = FlagshipAgentSDK()
    sample_doc = tmp_path / "paper.md"
    sample_doc.write_text("# Optical Bench\nFresnel dielectric 0.04.\n", encoding="utf-8")

    trace = sdk.run_workflow([
        {"tool": "gather.deconstruct", "args": {"path": str(sample_doc), "out_dir": str(tmp_path / "out")}},
        {"tool": "superframe.synthesize_material", "args": {"material_id": "gold_measured", "illuminant": "D65"}},
        {"tool": "flywheel.verify_three_plate", "args": {"artifact_path": str(sample_doc), "strict": True}},
    ])
    assert trace["ok"] and trace["verdict"] == "MATCH"
    assert trace["steps_completed"] == 3 and trace["steps_total"] == 3
    ok, errs, head = verify_workflow_trace(trace)
    assert ok and not errs and head == trace["trace_head"] and len(head) == 64

    # Planted 1-byte tamper in workflow trace step must be caught.
    tampered = copy.deepcopy(trace)
    tampered["steps"][1]["verdict"] = "MATCX"
    t_ok, t_errs, _ = verify_workflow_trace(tampered)
    assert not t_ok and any("step_hash mismatch" in e for e in t_errs)

    # Planted reorder of steps must be caught.
    reordered = copy.deepcopy(trace)
    reordered["steps"] = list(reversed(reordered["steps"]))
    r_ok, r_errs, _ = verify_workflow_trace(reordered)
    assert not r_ok and r_errs


def test_planted_unknown_tool_and_invalid_args_fail_closed():
    sdk = FlagshipAgentSDK()

    r_unknown = sdk.invoke("gather.deconstrct", {"path": "x.md"})
    assert not r_unknown["ok"] and r_unknown["verdict"] == "UNKNOWN_TOOL" and not r_unknown["executed"]
    assert "gather.deconstruct" in r_unknown["suggestions"]
    assert r_unknown["receipt_ready"] and r_unknown["call_sha256"].startswith("sha256:")

    r_missing = sdk.invoke("superframe.forge_meshlet_glb", {"kind": "boulder"})
    assert not r_missing["ok"] and r_missing["verdict"] == "INVALID_ARGS" and not r_missing["executed"]
    assert any("seed" in e for e in r_missing["errors"])

    r_wrong_type = sdk.invoke("superframe.forge_meshlet_glb", {"kind": "boulder", "seed": True})
    assert not r_wrong_type["ok"] and r_wrong_type["verdict"] == "INVALID_ARGS" and not r_wrong_type["executed"]


def test_planted_unauthorized_and_destructive_calls_zero_side_effects():
    side_effects: list[str] = []
    sdk = FlagshipAgentSDK()
    sdk.register_adapter("flywheel.run_operator_plan", lambda args: (side_effects.append("mutated"), {"ok": True})[1])

    r_human = sdk.invoke("flywheel.run_operator_plan", {"actions": ["write"]})
    assert not r_human["ok"] and r_human["verdict"] == "NEEDS_HUMAN" and not r_human["executed"]
    assert side_effects == []

    readonly = AuthorityContext(allow_mutating=False)
    r_deny = sdk.invoke("gather.deconstruct", {"path": "a.md"}, authority=readonly)
    assert not r_deny["ok"] and r_deny["verdict"] == "DENY" and not r_deny["executed"]

    approved = AuthorityContext(human_approval_id="human-w6-001")
    r_ok = sdk.invoke("flywheel.run_operator_plan", {"actions": ["write"]}, authority=approved)
    assert r_ok["ok"] and r_ok["executed"] and side_effects == ["mutated"]


def test_planted_colab_data_gate_and_budget_cap_guards():
    sdk = FlagshipAgentSDK()

    r_nogo = sdk.invoke(
        "colab.emit_stage1_job_spec",
        {"job_id": "pretrain-1", "profile": "frontier_pretraining", "accelerator": "H100", "data_gate_passed": False},
    )
    assert not r_nogo["ok"] and r_nogo["verdict"] == "NO_GO_DATA_GATE"
    assert r_nogo["result"]["shards"] == []

    r_over = emit_colab_job_spec(
        ColabJobRequest("big-bench", "gpu_kernel_bench", accelerator="H100", num_workers=4, estimated_hours=5.0, compute_unit_cap=100.0)
    )
    assert not r_over["ok"] and r_over["verdict"] == "BUDGET_EXCEEDED"

    r_floor = emit_colab_job_spec(
        ColabJobRequest("small-phys", "physai_trajectories", accelerator="A100", target_trajectories=50_000, compute_unit_cap=100.0)
    )
    assert not r_floor["ok"] and r_floor["verdict"] == "BELOW_TRAJECTORY_FLOOR"

    r_stage1 = emit_colab_job_spec(
        ColabJobRequest("phys-200k", "physai_trajectories", accelerator="A100", num_workers=2, estimated_hours=2.0, compute_unit_cap=100.0)
    )
    assert r_stage1["ok"] and r_stage1["verdict"] == "READY"
    assert len(r_stage1["shards"]) == 2 and r_stage1["target_trajectories"] == 200_000
    assert r_stage1["spec_sha256"].startswith("sha256:")
