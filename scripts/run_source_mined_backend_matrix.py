"""Run source-mined benchmark prompts across configured chat backends."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.agent_recovery_bench import DryEchoBackend
from harness.endpoints import build_endpoints
from harness.local_agent import OllamaBackend, ServeBackend
from harness.source_mined_bench import run_source_mined_backend_benchmark
from scripts.model_card_benchmark_shapes import (
    DEFAULT_ADVERSARIAL_DATASET,
    DEFAULT_UNISONAI_DATASET,
    DEFAULT_BUILDLANG_DATASET,
    DEFAULT_MODEL_DATASET,
    DEFAULT_AGENT_FRAMEWORK_DATASET,
    DEFAULT_ALIGNMENT_DATASET,
    DEFAULT_PUBLIC_THINKER_DATASET,
    DEFAULT_RESEARCH_DATASET,
    DEFAULT_SOCIAL_DATASET,
    benchmark_cases,
    load_datasets,
)


ONLINE_PROVIDERS = {"codex", "claude", "opencode", "open-code"}


def _split_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _filter_cases(
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


def _skipped(provider: str, reason: str) -> dict[str, Any]:
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
        "results": [],
    }


def _backend_for_provider(
    provider: str,
    *,
    serve_url: str,
    ollama_url: str,
    model: str,
    endpoint_model: str,
    modes: list[str],
    allow_online: bool,
) -> tuple[Any | None, dict[str, Any]]:
    provider = provider.lower().strip()
    if provider in ONLINE_PROVIDERS and not allow_online:
        return None, _skipped(provider, "online provider skipped; pass --allow-online to run")

    if provider == "dry":
        return DryEchoBackend(name="source-mined-dry", model_ref="dry:source-mined"), {}

    if provider == "serve":
        backend = ServeBackend(base_url=serve_url, name="source-mined-serve")
        if not backend.health():
            return None, _skipped(provider, f"serve backend unhealthy at {serve_url}")
        return backend, {"live": True}

    if provider == "ollama":
        backend = OllamaBackend(base_url=ollama_url, model=model, name="source-mined-ollama")
        if not backend.health():
            return None, _skipped(provider, f"ollama backend unhealthy at {ollama_url}")
        if getattr(backend, "_resolved", ""):
            backend.name = f"source-mined-ollama:{backend._resolved}"
        return backend, {"live": True}

    endpoint_provider = "opencode" if provider == "open-code" else provider
    model_env = f"{endpoint_provider.upper().replace('-', '_')}_MODEL"
    old_model = os.environ.get(model_env)
    if endpoint_model:
        os.environ[model_env] = endpoint_model
    try:
        backends = build_endpoints(providers=[endpoint_provider], modes=tuple(modes))
    finally:
        if endpoint_model:
            if old_model is None:
                os.environ.pop(model_env, None)
            else:
                os.environ[model_env] = old_model
    if not backends:
        return None, _skipped(
            provider,
            f"no configured endpoint backend for provider={provider} modes={','.join(modes)}",
        )
    return backends[0], {"live": True, "requested_model": endpoint_model}


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Source-mined Backend Matrix",
        "",
        f"- timestamp_utc: {report['timestamp_utc']}",
        f"- out_root: {report['out_root']}",
        f"- providers_requested: {', '.join(report['providers_requested'])}",
        f"- allow_online: {report['allow_online']}",
        f"- max_cases: {report['max_cases']}",
        f"- rows: {len(report['rows'])}",
        f"- operational_rows: {report['summary']['operational_rows']}",
        f"- skipped_rows: {report['summary']['skipped_rows']}",
        f"- mean_pass_rate: {report['summary']['mean_pass_rate']}",
        f"- mean_quality_score: {report['summary'].get('mean_quality_score', 0.0)}",
        f"- mean_reliability_score: {report['summary'].get('mean_reliability_score', 0.0)}",
        "",
        "| Provider | Backend | Live | Operational | Skipped | Cases | Pass rate | Quality | Reliability | Response rate | Error rate | Timeout rate | Receipts | Mean latency ms | Failure classes |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["rows"]:
        aggregates = row.get("aggregate_metrics", {})
        failures = aggregates.get("failure_class_counts", {})
        failure_text = ", ".join(f"{key}:{value}" for key, value in sorted(failures.items()))
        lines.append(
            "| "
            f"{row['provider']} | "
            f"{row.get('backend_name', '')} | "
            f"{row.get('live', False)} | "
            f"{row.get('operational', False)} | "
            f"{row.get('skipped', False)} | "
            f"{row.get('case_count', 0)} | "
            f"{row.get('pass_rate', 0.0)} | "
            f"{aggregates.get('mean_quality_score', 0.0)} | "
            f"{aggregates.get('mean_reliability_score', 0.0)} | "
            f"{row.get('response_present_rate', 0.0)} | "
            f"{aggregates.get('error_rate', 0.0)} | "
            f"{aggregates.get('timeout_rate', 0.0)} | "
            f"{row.get('receipt_completeness', 0.0)} | "
            f"{row.get('mean_latency_ms', 0.0)} | "
            f"{failure_text} |"
        )
    return "\n".join(lines) + "\n"


def _row_aggregate(row: dict[str, Any], metric: str) -> float:
    if row.get("skipped"):
        return 0.0
    value = row.get("aggregate_metrics", {}).get(metric, 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--providers", default="dry,serve,ollama,codex,claude,opencode")
    parser.add_argument("--allow-online", action="store_true")
    parser.add_argument("--modes", default="plan,api,provider,cloud")
    parser.add_argument("--serve-url", default="http://127.0.0.1:8765")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="", help="local/Ollama model selector")
    parser.add_argument("--endpoint-model", default="", help="remote endpoint model selector")
    parser.add_argument("--max-cases", type=int, default=2)
    parser.add_argument("--case-id", default="", help="comma-separated benchmark case ids")
    parser.add_argument("--category", default="", help="comma-separated benchmark categories")
    parser.add_argument("--backend-timeout-seconds", type=int, default=120)
    parser.add_argument("--out-root", default="C:/tmp/source_mined_backend_matrix")
    parser.add_argument("--model-dataset", type=Path, default=DEFAULT_MODEL_DATASET)
    parser.add_argument("--social-dataset", type=Path, default=DEFAULT_SOCIAL_DATASET)
    parser.add_argument("--research-dataset", type=Path, default=DEFAULT_RESEARCH_DATASET)
    parser.add_argument("--public-thinker-dataset", type=Path, default=DEFAULT_PUBLIC_THINKER_DATASET)
    parser.add_argument("--alignment-dataset", type=Path, default=DEFAULT_ALIGNMENT_DATASET)
    parser.add_argument("--agent-framework-dataset", type=Path, default=DEFAULT_AGENT_FRAMEWORK_DATASET)
    parser.add_argument("--buildlang-dataset", type=Path, default=DEFAULT_BUILDLANG_DATASET)
    parser.add_argument("--adversarial-dataset", type=Path, default=DEFAULT_ADVERSARIAL_DATASET)
    parser.add_argument("--unisonai-dataset", type=Path, default=DEFAULT_UNISONAI_DATASET)
    args = parser.parse_args(argv)

    out_root = Path(args.out_root).resolve()
    run_root = out_root / datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    run_root.mkdir(parents=True, exist_ok=True)

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
    cases = benchmark_cases(datasets)
    cases = _filter_cases(
        cases,
        case_ids=_split_csv(args.case_id),
        categories=_split_csv(args.category),
    )
    if not cases:
        sys.stderr.write("no benchmark cases matched --case-id/--category filters\n")
        return 2
    providers = _split_csv(args.providers)
    modes = _split_csv(args.modes) or ["plan", "api", "provider", "cloud"]
    rows: list[dict[str, Any]] = []
    for provider in providers:
        backend, metadata = _backend_for_provider(
            provider,
            serve_url=args.serve_url,
            ollama_url=args.ollama_url,
            model=args.model,
            endpoint_model=args.endpoint_model,
            modes=modes,
            allow_online=args.allow_online,
        )
        if backend is None:
            rows.append(metadata)
            continue
        if hasattr(backend, "timeout"):
            try:
                backend.timeout = min(int(getattr(backend, "timeout")), args.backend_timeout_seconds)
            except (TypeError, ValueError):
                backend.timeout = args.backend_timeout_seconds
        row = run_source_mined_backend_benchmark(
            cases,
            backend,
            provider=provider,
            max_cases=args.max_cases,
            timeout_seconds=args.backend_timeout_seconds,
        )
        row.update(metadata)
        row.update({
            "live": bool(metadata.get("live", False)),
            "operational": row["response_present_rate"] > 0 and row["receipt_completeness"] > 0,
            "skipped": False,
        })
        rows.append(row)

    pass_rates = [row["pass_rate"] for row in rows if not row.get("skipped")]
    quality_scores = [_row_aggregate(row, "mean_quality_score") for row in rows if not row.get("skipped")]
    reliability_scores = [
        _row_aggregate(row, "mean_reliability_score") for row in rows if not row.get("skipped")
    ]
    error_rates = [_row_aggregate(row, "error_rate") for row in rows if not row.get("skipped")]
    timeout_rates = [_row_aggregate(row, "timeout_rate") for row in rows if not row.get("skipped")]
    report = {
        "schema": "source-mined.backend-matrix/v1",
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "out_root": str(run_root),
        "providers_requested": providers,
        "allow_online": args.allow_online,
        "max_cases": args.max_cases,
        "backend_timeout_seconds": args.backend_timeout_seconds,
        "rows": rows,
        "summary": {
            "operational_rows": sum(1 for row in rows if row.get("operational")),
            "skipped_rows": sum(1 for row in rows if row.get("skipped")),
            "live_rows": sum(1 for row in rows if row.get("live")),
            "mean_pass_rate": round(sum(pass_rates) / len(pass_rates), 3) if pass_rates else 0.0,
            "mean_quality_score": round(sum(quality_scores) / len(quality_scores), 3)
            if quality_scores else 0.0,
            "mean_reliability_score": round(sum(reliability_scores) / len(reliability_scores), 3)
            if reliability_scores else 0.0,
            "mean_error_rate": round(sum(error_rates) / len(error_rates), 3) if error_rates else 0.0,
            "mean_timeout_rate": round(sum(timeout_rates) / len(timeout_rates), 3) if timeout_rates else 0.0,
        },
    }
    out_json = run_root / "source_mined_backend_matrix.json"
    out_md = run_root / "source_mined_backend_matrix.md"
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    out_md.write_text(render_markdown(report), encoding="utf-8")
    print(f"out_json={out_json}")
    print(f"out_md={out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
