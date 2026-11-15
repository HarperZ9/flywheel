"""Framework evidence adapters: wrap incumbents as evidence inputs.

Each importer maps a framework export (MLflow run, W&B artifact, SLSA / in-toto
provenance, ...) into a common EvidenceImport: the source refs it can attest, and
-- crucially -- an explicit ``missing_binding`` naming the Telos proof-layer fields
that CANNOT be inferred from the raw export (authority, workspace state,
verification verdicts, decision). That declared gap is the answer to "how is this
not <incumbent> with a new UI?". Stdlib-only.
"""

from __future__ import annotations

import re
from typing import Any

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")

# Telos proof-layer fields no runtime/experiment/eval/supply-chain export supplies.
NON_INFERABLE = [
    "authority_receipts",
    "workspace_state",
    "verification_verdicts",
    "decision_summary",
]


def _is_hex64(value: Any) -> bool:
    return isinstance(value, str) and bool(_HEX64.fullmatch(value))


def _evidence_import(
    source: str,
    *,
    evidence_inputs: list[str],
    sources: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "source": source,
        "evidence_inputs": evidence_inputs,
        "sources": sources,
        "missing_binding": list(NON_INFERABLE),
    }


def import_mlflow_run(run: dict[str, Any]) -> dict[str, Any]:
    """MLflow run -> evidence import (params/metrics/tags/artifact_uri)."""
    info = run.get("info", {}) or {}
    data = run.get("data", {}) or {}
    sources = [{"ref": f"mlflow:run:{info.get('run_id', '')}"}]
    for metric in data.get("metrics", []) or []:
        if isinstance(metric, dict):
            sources.append(
                {"ref": f"mlflow:metric:{metric.get('key')}={metric.get('value')}"}
            )
    return _evidence_import(
        "mlflow",
        evidence_inputs=["params", "metrics", "tags", "artifact_uri"],
        sources=sources,
    )


def import_wandb_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    """Weights & Biases artifact -> evidence import (name/version/digest)."""
    source = {"ref": f"wandb:artifact:{artifact.get('name', '')}"}
    digest = artifact.get("digest")
    if _is_hex64(digest):
        source["sha256"] = digest
    return _evidence_import(
        "wandb",
        evidence_inputs=["name", "version", "digest", "metadata"],
        sources=[source],
    )


def import_slsa_provenance(provenance: dict[str, Any]) -> dict[str, Any]:
    """SLSA / in-toto provenance -> evidence import (subjects with digests)."""
    sources = []
    for subject in provenance.get("subject", []) or []:
        if not isinstance(subject, dict):
            continue
        entry = {"ref": f"slsa:subject:{subject.get('name', '')}"}
        sha = (subject.get("digest") or {}).get("sha256")
        if _is_hex64(sha):
            entry["sha256"] = sha
        sources.append(entry)
    return _evidence_import(
        "slsa",
        evidence_inputs=["subject", "predicate.builder", "predicate.buildType"],
        sources=sources,
    )


# --------------------------------------------------------------------------- #
# pass 0064 adapter matrix: eval/observability incumbents. Each preserves the
# tool's native reference objects as sources, then declares the same gap.
# --------------------------------------------------------------------------- #


def import_braintrust_experiment(experiment: dict[str, Any]) -> dict[str, Any]:
    """Braintrust experiment -> evidence import (experiment_id/trace_ref/eval_ref)."""
    sources = [{"ref": f"braintrust:experiment:{experiment.get('experiment_id', '')}"}]
    trace_ref = experiment.get("trace_ref")
    if trace_ref:
        sources.append({"ref": f"braintrust:trace:{trace_ref}"})
    eval_ref = experiment.get("eval_ref")
    if eval_ref:
        sources.append({"ref": f"braintrust:eval:{eval_ref}"})
    return _evidence_import(
        "braintrust",
        evidence_inputs=["experiment_id", "trace_ref", "eval_ref", "scores"],
        sources=sources,
    )


def import_arize_phoenix_span(span: dict[str, Any]) -> dict[str, Any]:
    """Arize Phoenix span -> evidence import (trace_id/span_id/annotation_ref)."""
    sources = [{"ref": f"phoenix:trace:{span.get('trace_id', '')}"}]
    span_id = span.get("span_id")
    if span_id:
        sources.append({"ref": f"phoenix:span:{span_id}"})
    annotation_ref = span.get("annotation_ref")
    if annotation_ref:
        sources.append({"ref": f"phoenix:annotation:{annotation_ref}"})
    return _evidence_import(
        "arize_phoenix",
        evidence_inputs=["trace_id", "span_id", "annotation_ref"],
        sources=sources,
    )


def import_promptfoo_eval(report: dict[str, Any]) -> dict[str, Any]:
    """promptfoo eval -> evidence import (eval_report/red_team_case/ci_result)."""
    sources = [{"ref": f"promptfoo:eval:{report.get('eval_report', '')}"}]
    red_team_case = report.get("red_team_case")
    if red_team_case:
        sources.append({"ref": f"promptfoo:red-team:{red_team_case}"})
    ci_result = report.get("ci_result")
    if ci_result:
        sources.append({"ref": f"promptfoo:ci:{ci_result}"})
    return _evidence_import(
        "promptfoo",
        evidence_inputs=["eval_report", "red_team_case", "ci_result"],
        sources=sources,
    )


def import_helicone_request(request: dict[str, Any]) -> dict[str, Any]:
    """Helicone request -> evidence import (request_id/provider_route/cost_ref)."""
    sources = [{"ref": f"helicone:request:{request.get('request_id', '')}"}]
    provider_route = request.get("provider_route")
    if provider_route:
        sources.append({"ref": f"helicone:route:{provider_route}"})
    cost_ref = request.get("cost_ref")
    if cost_ref:
        sources.append({"ref": f"helicone:cost:{cost_ref}"})
    return _evidence_import(
        "helicone",
        evidence_inputs=["request_id", "provider_route", "cost_ref"],
        sources=sources,
    )


def import_wandb_weave_call(call: dict[str, Any]) -> dict[str, Any]:
    """W&B Weave call -> evidence import (call_ref/evaluation_ref/dataset_ref)."""
    sources = [{"ref": f"weave:call:{call.get('call_ref', '')}"}]
    evaluation_ref = call.get("evaluation_ref")
    if evaluation_ref:
        sources.append({"ref": f"weave:evaluation:{evaluation_ref}"})
    dataset_ref = call.get("dataset_ref")
    if dataset_ref:
        sources.append({"ref": f"weave:dataset:{dataset_ref}"})
    return _evidence_import(
        "wandb_weave",
        evidence_inputs=["call_ref", "evaluation_ref", "dataset_ref"],
        sources=sources,
    )


def import_dvc_stage(stage: dict[str, Any]) -> dict[str, Any]:
    """DVC stage -> evidence import (dvc_stage/data_hash/pipeline_ref)."""
    source = {"ref": f"dvc:stage:{stage.get('dvc_stage', '')}"}
    data_hash = stage.get("data_hash")
    if _is_hex64(data_hash):
        source["sha256"] = data_hash
    sources = [source]
    pipeline_ref = stage.get("pipeline_ref")
    if pipeline_ref:
        sources.append({"ref": f"dvc:pipeline:{pipeline_ref}"})
    return _evidence_import(
        "dvc",
        evidence_inputs=["dvc_stage", "data_hash", "pipeline_ref"],
        sources=sources,
    )
