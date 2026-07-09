"""run_m7_eval.py — the M7 eval runner. Fires when the trained model lands.

Measures HARNESS LIFT on the held-out task set.
Default mode runs local verified_inference vs local single_shot, plus flat-N and no-search ablations.
Use --frontier to add an external frontier single-shot baseline and compare verified_inference against it.
Use --frontier-all (or --frontier-providers) to compare against the full existing endpoint ladder
across all configured providers/modes.

Usage (real, after training + `serve.py` with ADAPTER_PATH set to the checkpoint):
    py scripts/run_m7_eval.py --serve http://127.0.0.1:8765 --out m7_scorecard.json
Dry-run (no GPU, proves the runner end-to-end with reference solutions):
    py scripts/run_m7_eval.py --dry-run --out /tmp/m7_dry.json
Frontier-mode dry-run:
    py scripts/run_m7_eval.py --dry-run --frontier --out /tmp/m7_frontier_dry.json
Pin/compare against a prior scorecard:
    py scripts/run_m7_eval.py ... --pinned prior_scorecard.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.eval import (run_eval, compare, save_scorecard, load_scorecard,
                         delta_vs_pinned, ArmConfig, SINGLE_SHOT,
                         VERIFIED_INFERENCE, FLAT_N, NO_SEARCH)
from harness.oracle import PytestOracle
from harness.proposer import ServeProposer, StubProposer, ProposerOutput, prompt_hash
from harness.extract import extract_code
from harness.endpoints import build_endpoints, PROVIDERS
from harness.agent_recovery_bench import DryEchoBackend
from harness.benchmark_receipts import store_benchmark_outputs
from harness.tasks_lib import REGISTRY, materialize_all
from harness.tasks_hard import HARD_REGISTRY
from harness.tasks_expert import EXPERT_REGISTRY
from harness.task import load_task
from harness.local_agent import OllamaBackend, ServeBackend
from harness.providers import make_proposer, REGISTRY as MODEL_REGISTRY
from harness.provider_roles import annotate_provider_roles, provider_alias_map, provider_roles_for
from harness.source_mined_bench import run_source_mined_backend_benchmark
from harness.governed_agent_bench import (
    default_scenarios as governed_default_scenarios,
    run_backend_benchmark as run_governed_backend_benchmark,
    run_governed_agent_benchmark,
)
from scripts.model_card_benchmark_shapes import (
    DEFAULT_ALIGNMENT_DATASET,
    DEFAULT_ADVERSARIAL_DATASET,
    DEFAULT_AGENT_FRAMEWORK_DATASET,
    DEFAULT_BUILDLANG_DATASET,
    DEFAULT_UNISONAI_DATASET,
    DEFAULT_MODEL_DATASET,
    DEFAULT_PUBLIC_THINKER_DATASET,
    DEFAULT_RESEARCH_DATASET,
    DEFAULT_SOCIAL_DATASET,
    benchmark_cases,
    load_datasets,
)

FRONTIER_SINGLE_SHOT = ArmConfig(name="frontier_single_shot", n_candidates=1,
                                 label="frontier baseline analog")
ARMS = [SINGLE_SHOT, VERIFIED_INFERENCE, FLAT_N, NO_SEARCH]


def _split_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _canonical_hash(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _packet_integrity(data: dict[str, Any]) -> dict[str, Any]:
    stored = data.get("packet_sha256")
    if not isinstance(stored, str) or not stored:
        return {
            "stored_packet_sha256": stored or "",
            "computed_packet_sha256": "",
            "packet_hash_valid": False,
            "packet_hash_failure": "packet_sha256_missing",
        }
    without_packet_hash = dict(data)
    without_packet_hash.pop("packet_sha256", None)
    computed = _canonical_hash(without_packet_hash)
    return {
        "stored_packet_sha256": stored,
        "computed_packet_sha256": computed,
        "packet_hash_valid": stored == computed,
        "packet_hash_failure": "" if stored == computed else "packet_hash_mismatch",
    }


def _attached_witnesses(raw: str) -> list[dict[str, Any]]:
    witnesses: list[dict[str, Any]] = []
    for item in _split_csv(raw):
        path = Path(item)
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            witnesses.append({
                "path": str(path),
                "loaded": False,
                "error": str(exc),
                "verdict": "UNVERIFIABLE",
                "declared_verdict": "UNVERIFIABLE",
                "packet_hash_valid": False,
                "packet_hash_failure": "witness_load_failed",
            })
            continue
        witness = data.get("witness") if isinstance(data.get("witness"), dict) else {}
        flywheel = data.get("flywheel") if isinstance(data.get("flywheel"), dict) else {}
        input_block = data.get("input") if isinstance(data.get("input"), dict) else {}
        integrity = _packet_integrity(data)
        declared_verdict = str(flywheel.get("verdict", "UNVERIFIABLE"))
        verdict = declared_verdict
        failure_code = str(flywheel.get("failure_code", ""))
        if not integrity["packet_hash_valid"]:
            verdict = "DRIFT" if declared_verdict == "MATCH" else "UNVERIFIABLE"
            failure_code = failure_code or integrity["packet_hash_failure"]
        witnesses.append({
            "path": str(path),
            "loaded": True,
            "schema": data.get("schema"),
            "packet_sha256": data.get("packet_sha256"),
            "computed_packet_sha256": integrity["computed_packet_sha256"],
            "packet_hash_valid": integrity["packet_hash_valid"],
            "packet_hash_failure": integrity["packet_hash_failure"],
            "verdict": verdict,
            "declared_verdict": declared_verdict,
            "failure_code": failure_code,
            "byte_witness_id": witness.get("byte_witness_id", ""),
            "receipt_sha256": input_block.get("receipt_sha256", ""),
            "export_sha256": input_block.get("export_sha256", ""),
            "verification_attached": witness.get("verification_attached", False),
        })
    return witnesses


def _witness_summary(witnesses: list[dict[str, Any]]) -> dict[str, Any]:
    if not witnesses:
        return {
            "count": 0,
            "loaded_count": 0,
            "match_rate": 0.0,
            "unverifiable_count": 0,
            "drift_count": 0,
            "invalid_packet_hash_count": 0,
            "verified_match_count": 0,
        }
    loaded = [item for item in witnesses if item.get("loaded")]
    return {
        "count": len(witnesses),
        "loaded_count": len(loaded),
        "match_rate": round(
            sum(1 for item in loaded if item.get("verdict") == "MATCH") / max(1, len(loaded)),
            3,
        ),
        "unverifiable_count": sum(1 for item in witnesses if item.get("verdict") == "UNVERIFIABLE"),
        "drift_count": sum(1 for item in witnesses if item.get("verdict") == "DRIFT"),
        "invalid_packet_hash_count": sum(
            1 for item in witnesses if not item.get("packet_hash_valid", False)
        ),
        "verified_match_count": sum(
            1
            for item in loaded
            if item.get("verdict") == "MATCH"
            and item.get("packet_hash_valid")
            and item.get("verification_attached")
        ),
    }


def _witness_gate(witnesses: list[dict[str, Any]], *, required: bool) -> dict[str, Any]:
    summary = _witness_summary(witnesses)
    if not required:
        return {
            "required": False,
            "passed": True,
            "reason": "not_required",
            "summary": summary,
        }
    if not witnesses:
        return {
            "required": True,
            "passed": False,
            "reason": "no_witnesses_attached",
            "summary": summary,
        }
    failures: list[dict[str, Any]] = []
    for witness in witnesses:
        reasons: list[str] = []
        if not witness.get("loaded"):
            reasons.append("not_loaded")
        if witness.get("verdict") != "MATCH":
            reasons.append(f"verdict_{witness.get('verdict', 'missing')}")
        if not witness.get("packet_hash_valid"):
            reasons.append(str(witness.get("packet_hash_failure") or "packet_hash_invalid"))
        if not witness.get("verification_attached"):
            reasons.append("verification_not_attached")
        if reasons:
            failures.append({
                "path": witness.get("path", ""),
                "byte_witness_id": witness.get("byte_witness_id", ""),
                "reasons": reasons,
            })
    return {
        "required": True,
        "passed": not failures,
        "reason": "all_witnesses_match" if not failures else "witness_gate_failed",
        "summary": summary,
        "failures": failures,
    }


def _sanitize(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in name.lower())


def _filter_source_mined_cases(
    cases: list[dict[str, Any]],
    *,
    case_ids: list[str],
    categories: list[str],
) -> list[dict[str, Any]]:
    selected = cases
    if case_ids:
        wanted = set(case_ids)
        selected = [case for case in selected if str(case.get("id")) in wanted]
    if categories:
        wanted = set(categories)
        selected = [case for case in selected if str(case.get("category")) in wanted]
    return selected


def _skipped_source_mined(provider: str, reason: str) -> dict[str, Any]:
    return {
        "schema": "source-mined.backend-benchmark/v1",
        "provider": provider,
        "backend_name": "",
        "live": False,
        "operational": False,
        "skipped": True,
        "skip_reason": reason,
        "case_count": 0,
        "passed_cases": 0,
        "failed_cases": 0,
        "pass_rate": 0.0,
        "response_present_rate": 0.0,
        "receipt_completeness": 0.0,
        "mean_latency_ms": 0.0,
        "max_latency_ms": 0,
        "metric_count": 0,
        "aggregate_metrics": {
            "mean_quality_score": 0.0,
            "mean_reliability_score": 0.0,
            "mean_metric_mention_rate": 0.0,
            "mean_task_focus_score": 0.0,
            "timeout_rate": 0.0,
            "error_rate": 0.0,
            "failure_class_counts": {},
            "category_summary": {},
        },
        "results": [],
    }


def _skipped_governed(provider: str, reason: str) -> dict[str, Any]:
    return {
        "schema": "governed-agent-workflow-backend/v1",
        "provider": provider,
        "backend_name": "",
        "live": False,
        "operational": False,
        "skipped": True,
        "skip_reason": reason,
        "case_count": 0,
        "passed_cases": 0,
        "failed_cases": 0,
        "pass_rate": 0.0,
        "mean_quality_score": 0.0,
        "mean_latency_ms": 0.0,
        "receipt_completeness": 0.0,
        "error_rate": 0.0,
        "results": [],
    }


def _source_mined_backend_for_provider(provider: str, args, modes: tuple[str, ...]):
    provider = provider.lower().strip()
    if provider == "dry":
        return DryEchoBackend(name="m7-source-mined-dry", model_ref="dry:source-mined"), {
            "live": False,
            "m7_role": "dry_control",
        }
    if provider == "serve":
        backend = ServeBackend(base_url=args.serve, name="m7-source-mined-serve")
        if not backend.health():
            return None, _skipped_source_mined(provider, f"serve backend unhealthy at {args.serve}")
        return backend, {
            "live": True,
            "m7_role": "flywheel_local_serve",
            "requested_model": args.local_model or "14b-cpt-adapter",
        }
    if provider == "ollama":
        model = args.local_model or args.source_mined_ollama_model
        backend = OllamaBackend(
            base_url=args.source_mined_ollama_url,
            model=model,
            name="m7-source-mined-ollama",
        )
        if not backend.health():
            return None, _skipped_source_mined(
                provider,
                f"ollama backend unhealthy at {args.source_mined_ollama_url}",
            )
        if getattr(backend, "_resolved", ""):
            backend.name = f"m7-source-mined-ollama:{backend._resolved}"
        return backend, {
            "live": True,
            "m7_role": "flywheel_local_ollama",
            "requested_model": model,
        }

    endpoint_provider = "opencode" if provider == "open-code" else provider
    model = args.source_mined_endpoint_model or args.frontier_model
    backends = _build_endpoint_backends(
        providers=[endpoint_provider],
        modes=modes,
        model=model,
    )
    if not backends:
        return None, _skipped_source_mined(
            provider,
            f"no configured endpoint backend for provider={provider} modes={','.join(modes)}",
        )
    role = "codex_harness" if endpoint_provider == "codex" else f"{endpoint_provider}_harness"
    return backends[0], {
        "live": True,
        "m7_role": role,
        "requested_model": model,
    }


def _governed_backend_for_provider(provider: str, args, modes: tuple[str, ...]):
    provider = provider.lower().strip()
    if provider == "dry":
        return DryEchoBackend(name="m7-governed-dry", model_ref="dry:governed-agent"), {
            "live": False,
            "m7_role": "dry_control",
        }
    if provider == "serve":
        backend = ServeBackend(base_url=args.serve, name="m7-governed-serve")
        if not backend.health():
            return None, _skipped_governed(provider, f"serve backend unhealthy at {args.serve}")
        return backend, {
            "live": True,
            "m7_role": "flywheel_local_serve",
            "requested_model": args.local_model or "14b-cpt-adapter",
        }
    if provider == "ollama":
        model = args.local_model or args.source_mined_ollama_model
        backend = OllamaBackend(
            base_url=args.source_mined_ollama_url,
            model=model,
            name="m7-governed-ollama",
        )
        if not backend.health():
            return None, _skipped_governed(
                provider,
                f"ollama backend unhealthy at {args.source_mined_ollama_url}",
            )
        if getattr(backend, "_resolved", ""):
            backend.name = f"m7-governed-ollama:{backend._resolved}"
        return backend, {
            "live": True,
            "m7_role": "flywheel_local_ollama",
            "requested_model": model,
        }

    endpoint_provider = "opencode" if provider == "open-code" else provider
    model = args.governed_endpoint_model or args.frontier_model
    backends = _build_endpoint_backends(
        providers=[endpoint_provider],
        modes=modes,
        model=model,
    )
    if not backends:
        return None, _skipped_governed(
            provider,
            f"no configured endpoint backend for provider={provider} modes={','.join(modes)}",
        )
    role = "codex_harness" if endpoint_provider == "codex" else f"{endpoint_provider}_harness"
    return backends[0], {
        "live": True,
        "m7_role": role,
        "requested_model": model,
    }


def _row_float(row: dict[str, Any], path: tuple[str, ...], default: float = 0.0) -> float:
    current: Any = row
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    try:
        return float(current)
    except (TypeError, ValueError):
        return default


def _source_mined_comparisons(rows: list[dict[str, Any]]) -> dict[str, Any]:
    codex = next((row for row in rows if row.get("provider") == "codex"), None)
    flywheel = next(
        (row for row in rows if row.get("provider") in {"serve", "ollama"} and not row.get("skipped")),
        None,
    )
    if not codex or not flywheel:
        return {"available": False, "reason": "need codex plus serve or ollama row"}
    return {
        "available": True,
        "flywheel_provider": flywheel.get("provider"),
        "codex_provider": codex.get("provider"),
        "pass_rate_delta_flywheel_minus_codex": round(
            float(flywheel.get("pass_rate", 0.0)) - float(codex.get("pass_rate", 0.0)),
            3,
        ),
        "quality_delta_flywheel_minus_codex": round(
            _row_float(flywheel, ("aggregate_metrics", "mean_quality_score"))
            - _row_float(codex, ("aggregate_metrics", "mean_quality_score")),
            3,
        ),
        "latency_delta_ms_flywheel_minus_codex": round(
            float(flywheel.get("mean_latency_ms", 0.0)) - float(codex.get("mean_latency_ms", 0.0)),
            3,
        ),
    }


def _governed_comparisons(rows: list[dict[str, Any]]) -> dict[str, Any]:
    codex = next((row for row in rows if row.get("provider") == "codex"), None)
    flywheel = next(
        (row for row in rows if row.get("provider") in {"serve", "ollama"} and not row.get("skipped")),
        None,
    )
    if not codex or not flywheel:
        return {"available": False, "reason": "need codex plus serve or ollama row"}
    return {
        "available": True,
        "flywheel_provider": flywheel.get("provider"),
        "codex_provider": codex.get("provider"),
        "pass_rate_delta_flywheel_minus_codex": round(
            float(flywheel.get("pass_rate", 0.0)) - float(codex.get("pass_rate", 0.0)),
            3,
        ),
        "quality_delta_flywheel_minus_codex": round(
            float(flywheel.get("mean_quality_score", 0.0))
            - float(codex.get("mean_quality_score", 0.0)),
            3,
        ),
        "latency_delta_ms_flywheel_minus_codex": round(
            float(flywheel.get("mean_latency_ms", 0.0)) - float(codex.get("mean_latency_ms", 0.0)),
            3,
        ),
    }


def _governed_schematic_gate(metrics: dict[str, Any]) -> dict[str, Any]:
    pass_rate = float(metrics.get("pass_rate", 0.0))
    doc_drift = float(metrics.get("mean_docs_schematic_drift_score", 0.0))
    graph_coverage = float(metrics.get("mean_execution_graph_coverage", 0.0))
    organic_doc = float(metrics.get("mean_organic_doc_update_score", 0.0))
    unauthorized = int(metrics.get("unauthorized_write_count", 0))
    unsafe = int(metrics.get("unsafe_mutation_count", 0))
    match = (
        pass_rate >= 1.0
        and doc_drift >= 1.0
        and graph_coverage >= 1.0
        and organic_doc >= 1.0
        and unauthorized == 0
        and unsafe == 0
    )
    return {
        "verdict": "MATCH" if match else "DRIFT",
        "pass_rate": pass_rate,
        "docs_schematic_drift_score": doc_drift,
        "execution_graph_coverage": graph_coverage,
        "organic_doc_update_score": organic_doc,
        "unauthorized_write_count": unauthorized,
        "unsafe_mutation_count": unsafe,
    }


def run_governed_agent_m7(args) -> int:
    scenarios = governed_default_scenarios()
    deterministic = run_governed_agent_benchmark(
        scenarios,
        max_scenarios=args.governed_max_scenarios,
    )

    modes = tuple(_split_csv(args.frontier_modes)) or ("plan", "api", "provider", "cloud")
    providers = _split_csv(args.governed_providers)
    if not providers:
        providers = ["dry"] if args.dry_run else ["serve", "codex"]

    rows: list[dict[str, Any]] = []
    for provider in providers:
        backend, metadata = _governed_backend_for_provider(provider, args, modes)
        if backend is None:
            rows.append(metadata)
            continue
        if hasattr(backend, "timeout"):
            try:
                backend.timeout = min(
                    int(getattr(backend, "timeout")),
                    args.governed_backend_timeout_seconds,
                )
            except (TypeError, ValueError):
                backend.timeout = args.governed_backend_timeout_seconds
        row = run_governed_backend_benchmark(
            scenarios,
            backend,
            provider=provider,
            max_scenarios=args.governed_backend_max_scenarios,
            timeout_seconds=args.governed_backend_timeout_seconds,
            max_tokens=args.governed_backend_max_tokens,
        )
        row.update(metadata)
        row.update({
            "live": bool(metadata.get("live", False)),
            "operational": row["case_count"] > 0 and row["receipt_completeness"] > 0,
            "skipped": False,
        })
        rows.append(row)

    annotate_provider_roles(rows)
    provider_roles = provider_roles_for(providers)
    gate = _governed_schematic_gate(deterministic["metrics"])
    attached_witnesses = _attached_witnesses(args.attached_witness)
    witness_gate = _witness_gate(attached_witnesses, required=args.require_witness_match)
    report = {
        "schema": "m7-governed-agent-scorecard/v1",
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "scenario_ids": [scenario.scenario_id for scenario in scenarios],
        "providers_requested": providers,
        "frontier_model": args.frontier_model,
        "governed_endpoint_model": args.governed_endpoint_model or args.frontier_model,
        "deterministic": deterministic,
        "backend_rows": rows,
        "provider_roles_requested": provider_roles,
        "provider_aliases": provider_alias_map(),
        "attached_witnesses": attached_witnesses,
        "summary": {
            "deterministic_pass_rate": deterministic["metrics"]["pass_rate"],
            "deterministic_quality": deterministic["metrics"]["mean_quality_score"],
            "schematic_release_gate": gate,
            "provider_role_ids": provider_roles,
            "operational_rows": sum(1 for row in rows if row.get("operational")),
            "skipped_rows": sum(1 for row in rows if row.get("skipped")),
            "live_rows": sum(1 for row in rows if row.get("live")),
            "comparison": _governed_comparisons(rows),
            "attached_witness_summary": _witness_summary(attached_witnesses),
            "witness_gate": witness_gate,
        },
        "schematic_contract": {
            "required_artifacts": [
                "execution_graph",
                "blast_radius",
                "change_receipt",
                "doc_delta",
            ],
            "release_gate_metrics": [
                "docs_schematic_drift_score",
                "execution_graph_coverage",
                "organic_doc_update_score",
                "unauthorized_write_count",
                "unsafe_mutation_count",
            ],
        },
        "note": "M7 governed-agent mode promotes documentation/schematic drift and accountable workflow checks into the scorecard.",
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    store_outputs = store_benchmark_outputs(
        report,
        store_root=args.store_root,
        kind="m7_governed_agent_scorecard",
        run_id=args.run_id,
        verdict="BENCHMARK_GATE_PASS" if witness_gate["passed"] else "BENCHMARK_GATE_FAIL",
        artifact_paths=[(args.out, "m7-governed-agent-scorecard-json")],
    )
    print("=== M7 governed-agent eval (workflow + schematic gates) ===")
    print(f"  deterministic_pass_rate={report['summary']['deterministic_pass_rate']}")
    print(f"  schematic_release_gate={gate}")
    for row in rows:
        print(
            "  "
            f"{row.get('provider')}:{row.get('backend_name')} "
            f"pass_rate={row.get('pass_rate')} "
            f"quality={row.get('mean_quality_score', 0.0)} "
            f"latency_ms={row.get('mean_latency_ms')} "
            f"receipts={row.get('receipt_completeness')}"
        )
    print(f"  comparison -> {report['summary']['comparison']}")
    print(f"  witness_gate -> {witness_gate}")
    print(f"  scorecard -> {args.out}")
    if store_outputs:
        print(f"  store_outputs -> {json.dumps(store_outputs, sort_keys=True)}")
    return 0 if witness_gate["passed"] else 1


def run_source_mined_m7(args) -> int:
    datasets = load_datasets(
        args.model_dataset,
        args.social_dataset,
        args.research_dataset,
        args.public_thinker_dataset,
        args.alignment_dataset,
        args.agent_framework_dataset,
        args.buildlang_dataset,
        args.adversarial_dataset,
        args.unisonai_dataset,
    )
    cases = _filter_source_mined_cases(
        benchmark_cases(datasets),
        case_ids=_split_csv(args.source_mined_case_id),
        categories=_split_csv(args.source_mined_category),
    )
    if not cases:
        raise ValueError("no source-mined cases matched --source-mined-case-id/--source-mined-category")

    modes = tuple(_split_csv(args.frontier_modes)) or ("plan", "api", "provider", "cloud")
    providers = _split_csv(args.source_mined_providers)
    if not providers:
        providers = ["serve", "codex"]

    rows: list[dict[str, Any]] = []
    for provider in providers:
        backend, metadata = _source_mined_backend_for_provider(provider, args, modes)
        if backend is None:
            rows.append(metadata)
            continue
        if hasattr(backend, "timeout"):
            try:
                backend.timeout = min(
                    int(getattr(backend, "timeout")),
                    args.source_mined_backend_timeout_seconds,
                )
            except (TypeError, ValueError):
                backend.timeout = args.source_mined_backend_timeout_seconds
        row = run_source_mined_backend_benchmark(
            cases,
            backend,
            provider=provider,
            max_cases=args.source_mined_max_cases,
            timeout_seconds=args.source_mined_backend_timeout_seconds,
        )
        row.update(metadata)
        row.update({
            "live": bool(metadata.get("live", False)),
            "operational": row["response_present_rate"] > 0 and row["receipt_completeness"] > 0,
            "skipped": False,
        })
        rows.append(row)

    annotate_provider_roles(rows)
    provider_roles = provider_roles_for(providers)
    attached_witnesses = _attached_witnesses(args.attached_witness)
    witness_gate = _witness_gate(attached_witnesses, required=args.require_witness_match)
    report = {
        "schema": "m7-source-mined-scorecard/v1",
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "case_ids": [str(case.get("id")) for case in cases],
        "categories": sorted({str(case.get("category")) for case in cases}),
        "providers_requested": providers,
        "frontier_model": args.frontier_model,
        "source_mined_endpoint_model": args.source_mined_endpoint_model or args.frontier_model,
        "rows": rows,
        "backend_rows": rows,
        "provider_roles_requested": provider_roles,
        "provider_aliases": provider_alias_map(),
        "attached_witnesses": attached_witnesses,
        "summary": {
            "provider_role_ids": provider_roles,
            "operational_rows": sum(1 for row in rows if row.get("operational")),
            "skipped_rows": sum(1 for row in rows if row.get("skipped")),
            "live_rows": sum(1 for row in rows if row.get("live")),
            "comparison": _source_mined_comparisons(rows),
            "attached_witness_summary": _witness_summary(attached_witnesses),
            "witness_gate": witness_gate,
        },
        "note": "M7 source-mined mode compares Codex/frontier harness rows against flywheel/local rows on the same custom source-mined case set.",
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    store_outputs = store_benchmark_outputs(
        report,
        store_root=args.store_root,
        kind="m7_source_mined_scorecard",
        run_id=args.run_id,
        verdict="BENCHMARK_GATE_PASS" if witness_gate["passed"] else "BENCHMARK_GATE_FAIL",
        artifact_paths=[(args.out, "m7-source-mined-scorecard-json")],
    )
    print("=== M7 source-mined eval (same custom cases) ===")
    for row in rows:
        print(
            "  "
            f"{row.get('provider')}:{row.get('backend_name')} "
            f"pass_rate={row.get('pass_rate')} "
            f"quality={row.get('aggregate_metrics', {}).get('mean_quality_score', 0.0)} "
            f"latency_ms={row.get('mean_latency_ms')} "
            f"failures={row.get('aggregate_metrics', {}).get('failure_class_counts', {})}"
        )
    print(f"  comparison -> {report['summary']['comparison']}")
    print(f"  witness_gate -> {witness_gate}")
    print(f"  scorecard -> {args.out}")
    if store_outputs:
        print(f"  store_outputs -> {json.dumps(store_outputs, sort_keys=True)}")
    return 0 if witness_gate["passed"] else 1


def _build_endpoint_backends(*, providers: list[str] | None, modes: tuple[str, ...], model: str = ""):
    provider_names = providers if providers is not None else list(PROVIDERS)
    originals: dict[str, str | None] = {}
    if model:
        for provider in provider_names:
            env_name = f"{provider.upper().replace('-', '_')}_MODEL"
            originals[env_name] = os.environ.get(env_name)
            os.environ[env_name] = model
    try:
        return build_endpoints(providers=providers, modes=modes)
    finally:
        for env_name, original in originals.items():
            if original is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = original


class EndpointProposer:
    """Adapter: any endpoint backend becomes a Proposer for eval harness comparisons."""

    def __init__(self, backend):
        self.backend = backend
        self.model_ref = backend.name

    def generate(self, prompt: str, *, seed: int, temperature: float,
                 max_new_tokens: int, system: str = "") -> ProposerOutput:
        gen = self.backend.chat(
            [{"role": "user", "content": prompt}],
            system=system,
            max_tokens=max_new_tokens,
            temperature=temperature,
            seed=seed,
        )
        return ProposerOutput(
            text=extract_code(gen["text"]),
            model_ref=gen.get("model_ref", self.model_ref),
            seed=gen.get("seed", seed),
            prompt_hash=prompt_hash(prompt),
            cache="frontier",
        )


def _registry(tier: str):
    return {"expert": EXPERT_REGISTRY, "hard": HARD_REGISTRY}.get(tier, REGISTRY)


def build_task_set(workroot: Path, n: int, tier: str = "easy"):
    dirs = materialize_all(_registry(tier)[:n], workroot / "m7-tasks")
    return [load_task(d) for d in dirs]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", default="http://127.0.0.1:8765")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--hard", action="store_true", help="use the harder held-out set")
    ap.add_argument("--expert", action="store_true", help="use the EXPERT set (uplift headroom)")
    ap.add_argument("--n-tasks", type=int, default=0)
    ap.add_argument("--out", default="m7_scorecard.json")
    ap.add_argument("--store-root", default="")
    ap.add_argument("--run-id", default="")
    ap.add_argument("--pinned", default="")
    ap.add_argument("--workroot", default=str(Path(__file__).parent.parent / ".m7-run"))
    ap.add_argument("--frontier", action="store_true",
                    help="compare verified_inference against frontier single-shot")
    ap.add_argument("--frontier-provider", default="codex",
                    help="provider name for frontier proposer (default: codex)")
    ap.add_argument("--frontier-model", default="gpt-5.3-codex-spark",
                    help="model name for frontier baseline")
    ap.add_argument("--baseline-provider", default="",
                    help="optional: use this provider for VERIFIED_INFERENCE/SINGLE_SHOT/base arms")
    ap.add_argument("--baseline-model", default="",
                    help="optional model for --baseline-provider (defaults to frontier-model when unset)")
    ap.add_argument("--baseline-base-url", default="",
                    help="optional base URL override for --baseline-provider")
    ap.add_argument("--baseline-modes", default="plan,api,provider,cloud",
                    help="modes to use when resolving --baseline-provider")
    ap.add_argument("--frontier-base-url", default="",
                    help="override base URL for frontier proposer")
    ap.add_argument("--frontier-only", action="store_true",
                    help="run frontier-backed benchmark without local serve dependency")
    ap.add_argument("--frontier-all", action="store_true",
                    help="use all configured providers/modes from endpoints.py as frontier arms")
    ap.add_argument("--frontier-providers", default="",
                    help="comma list of providers for frontier-mode (implies multi-backend frontier)")
    ap.add_argument("--frontier-modes", default="plan,api,provider,cloud",
                    help="comma list of endpoint modes for frontier backend expansion")
    ap.add_argument("--local", action="store_true",
                    help="compare local-provider single-shot baselines")
    ap.add_argument("--local-provider", default="",
                    help="comma list of local providers for local baseline sweep "
                         "(default: all local providers in providers.REGISTRY plus 'serve')")
    ap.add_argument("--local-model", default="",
                    help="override model name for all local baseline providers")
    ap.add_argument("--local-primary", default="serve",
                    help="local proposer for verified_inference (default: serve)")
    ap.add_argument("--attached-witness", default="",
                    help="comma list of byte-witness JSON packets to attach to M7 source-mined/governed scorecards")
    ap.add_argument("--require-witness-match", action="store_true",
                    help="fail source-mined/governed M7 runs unless every attached witness is a verified MATCH with a valid packet hash")
    ap.add_argument("--source-mined", action="store_true",
                    help="run source-mined custom benchmark cases through the M7 comparison entrypoint")
    ap.add_argument("--governed-agent", action="store_true",
                    help="run governed-agent workflow and schematic drift checks through the M7 entrypoint")
    ap.add_argument("--governed-providers", default="",
                    help="comma list of governed-agent providers; default is dry for --dry-run else serve,codex")
    ap.add_argument("--governed-max-scenarios", type=int, default=0,
                    help="limit deterministic governed-agent scenarios; 0 means all")
    ap.add_argument("--governed-backend-max-scenarios", type=int, default=2,
                    help="limit backend governed-agent explanation scenarios")
    ap.add_argument("--governed-backend-timeout-seconds", type=int, default=120)
    ap.add_argument("--governed-backend-max-tokens", type=int, default=300)
    ap.add_argument("--governed-endpoint-model", default="",
                    help="endpoint model for governed-agent rows; defaults to --frontier-model")
    ap.add_argument("--source-mined-providers", default="serve,codex",
                    help="comma list of source-mined providers (default: serve,codex)")
    ap.add_argument("--source-mined-case-id", default="",
                    help="comma list of source-mined benchmark case ids")
    ap.add_argument("--source-mined-category", default="",
                    help="comma list of source-mined benchmark categories")
    ap.add_argument("--source-mined-max-cases", type=int, default=0,
                    help="limit matched source-mined cases; 0 means all matched cases")
    ap.add_argument("--source-mined-backend-timeout-seconds", type=int, default=120)
    ap.add_argument("--source-mined-endpoint-model", default="",
                    help="endpoint model for source-mined rows; defaults to --frontier-model")
    ap.add_argument("--source-mined-ollama-url", default="http://127.0.0.1:11434")
    ap.add_argument("--source-mined-ollama-model", default="qwen2.5:7b")
    ap.add_argument("--model-dataset", type=Path, default=DEFAULT_MODEL_DATASET)
    ap.add_argument("--social-dataset", type=Path, default=DEFAULT_SOCIAL_DATASET)
    ap.add_argument("--research-dataset", type=Path, default=DEFAULT_RESEARCH_DATASET)
    ap.add_argument("--public-thinker-dataset", type=Path, default=DEFAULT_PUBLIC_THINKER_DATASET)
    ap.add_argument("--alignment-dataset", type=Path, default=DEFAULT_ALIGNMENT_DATASET)
    ap.add_argument("--agent-framework-dataset", type=Path, default=DEFAULT_AGENT_FRAMEWORK_DATASET)
    ap.add_argument("--buildlang-dataset", type=Path, default=DEFAULT_BUILDLANG_DATASET)
    ap.add_argument("--adversarial-dataset", type=Path, default=DEFAULT_ADVERSARIAL_DATASET)
    ap.add_argument("--unisonai-dataset", type=Path, default=DEFAULT_UNISONAI_DATASET)
    a = ap.parse_args()

    if a.governed_agent:
        return run_governed_agent_m7(a)

    if a.source_mined or a.source_mined_case_id or a.source_mined_category:
        return run_source_mined_m7(a)

    tier = "expert" if a.expert else ("hard" if a.hard else "easy")
    n = a.n_tasks or len(_registry(tier))
    workroot = Path(a.workroot)
    task_set = build_task_set(workroot, n, tier=tier)

    frontier_arms: list[ArmConfig] = []
    frontier_proposers: dict[str, object] = {}
    frontier_meta: dict[str, str] = {}
    frontier_modes = tuple(_split_csv(a.frontier_modes))
    if not frontier_modes:
        frontier_modes = ("plan", "api", "provider", "cloud")

    local_arms: list[ArmConfig] = []
    local_proposers: dict[str, object] = {}
    local_meta: dict[str, str] = {}
    local_provider_names = [p for p, spec in MODEL_REGISTRY.items() if spec.local]
    if "serve" not in local_provider_names:
        local_provider_names.append("serve")
    if not local_provider_names:
        local_provider_names = ["serve"]

    if a.local:
        local_providers = _split_csv(a.local_provider) or local_provider_names
        for pname in local_providers:
            if pname == "serve":
                local_model = a.local_model or "14b-cpt-adapter"
                arm_name = f"local_{_sanitize(pname)}"
                local_arms.append(ArmConfig(
                    name=arm_name,
                    n_candidates=1,
                    label=f"local ({pname})",
                ))
                local_meta[arm_name] = f"{pname}:{local_model}"
                if not a.dry_run:
                    local_proposers[arm_name] = ServeProposer(
                        base_url=a.serve,
                        model_ref=local_model)
                else:
                    local_proposers[arm_name] = StubProposer(
                        "pass\n", model_ref=local_meta[arm_name])
                continue

            if pname not in MODEL_REGISTRY:
                known_local = ", ".join(sorted(set(MODEL_REGISTRY) | {"serve"}))
                raise ValueError(f"unknown local provider {pname!r} (known: {known_local})")
            if not MODEL_REGISTRY[pname].local:
                raise ValueError(f"{pname!r} is not local; pass --frontier for remote providers")
            arm_name = f"local_{_sanitize(pname)}"
            local_arms.append(ArmConfig(
                name=arm_name,
                n_candidates=1,
                label=f"local ({pname})",
            ))
            local_model = a.local_model or MODEL_REGISTRY[pname].default_model
            local_meta[arm_name] = f"{pname}:{local_model}"
            if not a.dry_run:
                local_proposers[arm_name] = make_proposer(
                    pname, model=local_model or None, base_url=None
                )
            else:
                local_proposers[arm_name] = StubProposer("pass\n", model_ref=local_meta[arm_name])

    if a.frontier and not a.dry_run and (a.frontier_all or a.frontier_providers):
        providers = _split_csv(a.frontier_providers) or None
        backends = _build_endpoint_backends(
            providers=providers,
            modes=frontier_modes,
            model=a.frontier_model,
        )
        if not backends:
            raise ValueError(
                "frontier requested but no configured endpoint backends found; "
                "set provider credentials or run with --frontier-providers and --dry-run")
        for backend in backends:
            arm_name = f"frontier_{_sanitize(backend.name)}"
            frontier_arms.append(ArmConfig(
                name=arm_name,
                n_candidates=1,
                label=f"frontier ({backend.name})",
            ))
            frontier_proposers[arm_name] = EndpointProposer(backend)
            backend_model = getattr(backend, "model", backend.name.split("-", 1)[0])
            frontier_meta[arm_name] = f"{backend.name}:{backend_model}"

    if a.frontier and not frontier_arms and not a.dry_run and not a.frontier_all and not a.frontier_providers:
        p = make_proposer(
            a.frontier_provider,
            model=a.frontier_model,
            base_url=a.frontier_base_url or None
        )
        frontier_arms.append(FRONTIER_SINGLE_SHOT)
        frontier_proposers[FRONTIER_SINGLE_SHOT.name] = p
        frontier_meta[FRONTIER_SINGLE_SHOT.name] = f"{a.frontier_provider}:{a.frontier_model}"

    if a.frontier and a.dry_run and not frontier_arms:
        if a.frontier_all or a.frontier_providers:
            dry_providers = _split_csv(a.frontier_providers) or list(PROVIDERS)
            for pname in dry_providers:
                for mode in frontier_modes:
                    arm_name = f"frontier_{_sanitize(f'{pname}-{mode}')}"
                    frontier_arms.append(ArmConfig(
                        name=arm_name,
                        n_candidates=1,
                        label=f"frontier ({pname}-{mode})",
                    ))
                    frontier_meta[arm_name] = f"{pname}:{a.frontier_model}"
        else:
            frontier_arms.append(FRONTIER_SINGLE_SHOT)
            frontier_meta[FRONTIER_SINGLE_SHOT.name] = f"{a.frontier_provider}:{a.frontier_model}"
            frontier_proposers[FRONTIER_SINGLE_SHOT.name] = StubProposer(
                "pass\n",
                model_ref=frontier_meta[FRONTIER_SINGLE_SHOT.name]
            )
        # dry runs never call the live API/backends
        frontier_proposers = {name: StubProposer("pass\n", model_ref=meta)
                             for name, meta in frontier_meta.items()}

    if a.dry_run:
        ref = {s.task_id: s.solution for s in _registry(tier)}

        def proposer_for(arm, task):
            if arm.name in local_proposers:
                return local_proposers[arm.name]
            return StubProposer(ref.get(task.task_id, "pass\n"), model_ref="dry-run(reference)")

        model_ref = "dry-run(reference)"
    else:
        if a.baseline_provider:
            baseline_modes = tuple(_split_csv(a.baseline_modes)) or ("plan",)
            baseline_backends = _build_endpoint_backends(
                providers=[a.baseline_provider],
                modes=baseline_modes,
                model=a.baseline_model or a.frontier_model,
            )
            if baseline_backends:
                local_proposer = EndpointProposer(baseline_backends[0])
            else:
                local_proposer = make_proposer(
                    a.baseline_provider,
                    model=a.baseline_model or a.frontier_model,
                    base_url=a.baseline_base_url or a.frontier_base_url or None
                )
        elif a.frontier_only:
            local_proposer = make_proposer(
                a.frontier_provider,
                model=a.baseline_model or a.frontier_model,
                base_url=a.baseline_base_url or a.frontier_base_url or None
            )
        elif a.local_primary == "serve":
            local_proposer = ServeProposer(
                base_url=a.serve,
                model_ref=a.local_model or "14b-cpt-adapter")
        else:
            if a.local_primary not in MODEL_REGISTRY:
                raise ValueError(f"unknown local-primary provider {a.local_primary!r} (known: {', '.join(MODEL_REGISTRY)})")
            if not MODEL_REGISTRY[a.local_primary].local:
                raise ValueError(f"--local-primary requires a local provider, got {a.local_primary!r}")
            local_proposer = make_proposer(
                a.local_primary, model=a.local_model or None
            )

        def proposer_for(arm, task):
            if arm.name in local_proposers:
                return local_proposers[arm.name]
            if arm.name in frontier_proposers:
                proposer = frontier_proposers[arm.name]
                if isinstance(proposer, StubProposer):
                    return proposer
                return proposer
            return local_proposer

        model_ref = local_proposer.model_ref

    def oracle_for(task):
        return PytestOracle()

    arms = ARMS.copy()
    arms.extend(frontier_arms)
    arms.extend(local_arms)

    reports = run_eval(arms, task_set, proposer_for, oracle_for)
    print("=== M7 eval (harness lift on the held-out set) ===")
    for name, r in reports.items():
        print("  " + r.summary())

    if frontier_arms:
        for arm in frontier_arms:
            verdict = compare(reports, baseline=arm.name, candidate=VERIFIED_INFERENCE.name)
            print(f"  verdict (verified_inference >= {arm.name}): {verdict}")
    if local_arms:
        for arm in local_arms:
            verdict = compare(reports, baseline=arm.name, candidate=VERIFIED_INFERENCE.name)
            print(f"  verdict (verified_inference >= {arm.name}): {verdict}")
    else:
        verdict = compare(reports, baseline=SINGLE_SHOT.name, candidate=VERIFIED_INFERENCE.name)
        print(f"  verdict (verified_inference >= {SINGLE_SHOT.name}): {verdict}")

    meta = {"model_ref": model_ref, "n_tasks": len(task_set),
            "note": ("frontier single-shot baseline comparison"
                     if a.frontier else
                     "harness lift vs single-shot of the SAME model")}
    if a.frontier:
        meta["frontier_mode"] = "multi-endpoint" if frontier_proposers and len(frontier_arms) > 1 else "single"
        meta["frontier_arms"] = [arm.name for arm in frontier_arms]
        meta["frontier_model_refs"] = frontier_meta
        if frontier_meta and len(frontier_arms) == 1:
            only = frontier_arms[0]
            meta["frontier_model_ref"] = frontier_meta[only.name]
            if only.name == FRONTIER_SINGLE_SHOT.name:
                meta["frontier_provider"] = a.frontier_provider
    if a.local:
        meta["local_mode"] = "sweep"
        meta["local_arms"] = [arm.name for arm in local_arms]
        meta["local_model_refs"] = local_meta

    save_scorecard(a.out, reports, meta=meta)
    print(f"  scorecard -> {a.out}")
    store_outputs = store_benchmark_outputs(
        {
            "schema": "harness.m7-scorecard-artifact/v1",
            "out": a.out,
            "tier": tier,
            "n_tasks": len(task_set),
            "model_ref": model_ref,
            "frontier": bool(a.frontier),
            "local": bool(a.local),
            "dry_run": bool(a.dry_run),
        },
        store_root=a.store_root,
        kind="m7_scorecard",
        run_id=a.run_id,
        verdict="BENCHMARK_RECORDED",
        artifact_paths=[(a.out, "m7-scorecard-json")],
    )
    if store_outputs:
        print(f"  store_outputs -> {json.dumps(store_outputs, sort_keys=True)}")

    if a.pinned and Path(a.pinned).exists():
        d = delta_vs_pinned(reports, load_scorecard(a.pinned))
        print(f"  vs pinned {a.pinned}: {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
