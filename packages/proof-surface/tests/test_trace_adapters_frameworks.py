"""Framework evidence adapters: wrap incumbents, declare the non-inferable gap."""

from __future__ import annotations

from proof_surface.trace_adapters import (
    ADAPTER_COVERAGE,
    NON_INFERABLE,
    PRIORITY5_INCUMBENTS,
    import_arize_phoenix_span,
    import_braintrust_experiment,
    import_dvc_stage,
    import_helicone_request,
    import_mlflow_run,
    import_promptfoo_eval,
    import_slsa_provenance,
    import_wandb_artifact,
    import_wandb_weave_call,
    uncovered_priority5,
)

_HEX = "a" * 64


def test_mlflow_run_yields_sources_and_declares_missing_binding():
    ev = import_mlflow_run(
        {"info": {"run_id": "r1"}, "data": {"metrics": [{"key": "acc", "value": 0.9}]}}
    )
    assert ev["source"] == "mlflow"
    refs = [s["ref"] for s in ev["sources"]]
    assert "mlflow:run:r1" in refs
    assert any("acc" in r for r in refs)
    assert ev["missing_binding"] == NON_INFERABLE
    assert "authority_receipts" in ev["missing_binding"]


def test_wandb_artifact_binds_a_hex_digest():
    ev = import_wandb_artifact({"name": "model", "version": "v3", "digest": _HEX})
    assert ev["sources"][0]["sha256"] == _HEX
    assert ev["missing_binding"] == NON_INFERABLE


def test_slsa_provenance_binds_subject_digests():
    ev = import_slsa_provenance(
        {"subject": [{"name": "artifact.tar", "digest": {"sha256": _HEX}}]}
    )
    assert ev["sources"][0]["ref"] == "slsa:subject:artifact.tar"
    assert ev["sources"][0]["sha256"] == _HEX
    assert ev["missing_binding"] == NON_INFERABLE


def test_missing_binding_names_the_proof_layer_fields():
    # The declared gap is the differentiator: incumbents do not supply these.
    for field in ("authority_receipts", "workspace_state", "verification_verdicts"):
        assert field in NON_INFERABLE


# --------------------------------------------------------------------------- #
# pass 0064 adapter matrix: eval/observability incumbents (native refs kept)
# --------------------------------------------------------------------------- #


def test_braintrust_experiment_preserves_native_refs():
    ev = import_braintrust_experiment(
        {"experiment_id": "exp1", "trace_ref": "t9", "eval_ref": "e3"}
    )
    assert ev["source"] == "braintrust"
    refs = [s["ref"] for s in ev["sources"]]
    assert "braintrust:experiment:exp1" in refs
    assert "braintrust:trace:t9" in refs
    assert "braintrust:eval:e3" in refs
    assert ev["missing_binding"] == NON_INFERABLE


def test_arize_phoenix_span_preserves_trace_span_annotation():
    ev = import_arize_phoenix_span(
        {"trace_id": "tr1", "span_id": "sp1", "annotation_ref": "an1"}
    )
    assert ev["source"] == "arize_phoenix"
    refs = [s["ref"] for s in ev["sources"]]
    assert "phoenix:trace:tr1" in refs
    assert "phoenix:span:sp1" in refs
    assert "phoenix:annotation:an1" in refs
    assert ev["missing_binding"] == NON_INFERABLE


def test_promptfoo_eval_preserves_report_redteam_ci():
    ev = import_promptfoo_eval(
        {"eval_report": "r1", "red_team_case": "rt7", "ci_result": "ci4"}
    )
    assert ev["source"] == "promptfoo"
    refs = [s["ref"] for s in ev["sources"]]
    assert "promptfoo:eval:r1" in refs
    assert any("rt7" in r for r in refs)
    assert any("ci4" in r for r in refs)
    assert ev["missing_binding"] == NON_INFERABLE


def test_helicone_request_preserves_request_route_cost():
    ev = import_helicone_request(
        {"request_id": "req1", "provider_route": "openai/gpt", "cost_ref": "c2"}
    )
    assert ev["source"] == "helicone"
    refs = [s["ref"] for s in ev["sources"]]
    assert "helicone:request:req1" in refs
    assert any("openai/gpt" in r for r in refs)
    assert any("c2" in r for r in refs)
    assert ev["missing_binding"] == NON_INFERABLE


def test_wandb_weave_call_preserves_call_eval_dataset():
    ev = import_wandb_weave_call(
        {"call_ref": "call1", "evaluation_ref": "ev1", "dataset_ref": "ds1"}
    )
    assert ev["source"] == "wandb_weave"
    refs = [s["ref"] for s in ev["sources"]]
    assert "weave:call:call1" in refs
    assert "weave:evaluation:ev1" in refs
    assert "weave:dataset:ds1" in refs
    assert ev["missing_binding"] == NON_INFERABLE


def test_dvc_stage_binds_a_hex_data_hash():
    ev = import_dvc_stage(
        {"dvc_stage": "train", "data_hash": _HEX, "pipeline_ref": "dvc.yaml"}
    )
    assert ev["source"] == "dvc"
    assert ev["sources"][0]["ref"] == "dvc:stage:train"
    assert ev["sources"][0]["sha256"] == _HEX
    assert any("dvc.yaml" in s["ref"] for s in ev["sources"])
    assert ev["missing_binding"] == NON_INFERABLE


def test_dvc_stage_ignores_non_hex_data_hash():
    ev = import_dvc_stage({"dvc_stage": "train", "data_hash": "not-a-digest"})
    assert "sha256" not in ev["sources"][0]


def test_priority5_incumbents_are_all_covered():
    # The pass 0064 matrix ranks these tools priority 5; none may be uncovered.
    assert uncovered_priority5() == []
    for tool in PRIORITY5_INCUMBENTS:
        assert tool in ADAPTER_COVERAGE
        assert ADAPTER_COVERAGE[tool] is not None
