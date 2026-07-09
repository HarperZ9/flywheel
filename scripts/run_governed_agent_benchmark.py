"""Run governed-agent workflow benchmark and optional backend explanation rows."""

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
from harness.governed_agent_bench import (
    default_scenarios,
    run_backend_benchmark,
    run_governed_agent_benchmark,
)
from harness.local_agent import OllamaBackend, ServeBackend


ONLINE_PROVIDERS = {"codex", "claude", "opencode", "open-code"}


def _split_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _env_prefix(provider: str) -> str:
    return provider.upper().replace("-", "_")


def _backend_for_provider(provider: str, args) -> tuple[Any | None, dict[str, Any]]:
    provider = provider.lower().strip()
    if provider in ONLINE_PROVIDERS and not args.allow_online:
        return None, {
            "schema": "governed-agent-workflow-backend/v1",
            "provider": provider,
            "skipped": True,
            "skip_reason": "online provider skipped; pass --allow-online",
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
    if provider == "dry":
        return DryEchoBackend(name="governed-agent-dry", model_ref="dry:governed-agent"), {}
    if provider == "serve":
        backend = ServeBackend(base_url=args.serve_url, name="governed-agent-serve")
        if not backend.health():
            return None, _skipped(provider, f"serve backend unhealthy at {args.serve_url}")
        return backend, {"live": True}
    if provider == "ollama":
        backend = OllamaBackend(
            base_url=args.ollama_url,
            model=args.model,
            name="governed-agent-ollama",
        )
        if not backend.health():
            return None, _skipped(provider, f"ollama backend unhealthy at {args.ollama_url}")
        if getattr(backend, "_resolved", ""):
            backend.name = f"governed-agent-ollama:{backend._resolved}"
        return backend, {"live": True}

    endpoint_provider = "opencode" if provider == "open-code" else provider
    env_name = f"{_env_prefix(endpoint_provider)}_MODEL"
    old_model = os.environ.get(env_name)
    if args.endpoint_model:
        os.environ[env_name] = args.endpoint_model
    try:
        backends = build_endpoints(providers=[endpoint_provider], modes=tuple(_split_csv(args.modes)))
    finally:
        if args.endpoint_model:
            if old_model is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = old_model
    if not backends:
        return None, _skipped(provider, "no configured endpoint backend")
    return backends[0], {"live": True, "requested_model": args.endpoint_model}


def _skipped(provider: str, reason: str) -> dict[str, Any]:
    return {
        "schema": "governed-agent-workflow-backend/v1",
        "provider": provider,
        "skipped": True,
        "skip_reason": reason,
        "live": False,
        "operational": False,
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


def render_markdown(report: dict[str, Any]) -> str:
    det = report["deterministic"]
    lines = [
        "# Governed Agent Workflow Benchmark",
        "",
        f"- timestamp_utc: {report['timestamp_utc']}",
        f"- deterministic_scenarios: {det['scenario_count']}",
        f"- deterministic_pass_rate: {det['metrics']['pass_rate']}",
        f"- deterministic_quality: {det['metrics']['mean_quality_score']}",
        f"- backend_rows: {len(report['backend_rows'])}",
        "",
        "## Deterministic scenarios",
        "",
        "| Scenario | Tier | Passed | Quality | Events |",
        "|---|---|---:|---:|---:|",
    ]
    for result in det["results"]:
        lines.append(
            "| "
            f"{result['scenario_id']} | "
            f"{result['maturity_tier']} | "
            f"{result['passed']} | "
            f"{result['quality_score']} | "
            f"{result['event_count']} |"
        )
    lines.extend([
        "",
        "## Backend rows",
        "",
        "| Provider | Backend | Live | Skipped | Cases | Pass rate | Quality | Receipts | Error | Mean latency ms | Reason |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ])
    for row in report["backend_rows"]:
        lines.append(
            "| "
            f"{row.get('provider')} | "
            f"{row.get('backend_name', '')} | "
            f"{row.get('live', False)} | "
            f"{row.get('skipped', False)} | "
            f"{row.get('case_count', 0)} | "
            f"{row.get('pass_rate', 0.0)} | "
            f"{row.get('mean_quality_score', 0.0)} | "
            f"{row.get('receipt_completeness', 0.0)} | "
            f"{row.get('error_rate', 0.0)} | "
            f"{row.get('mean_latency_ms', 0.0)} | "
            f"{row.get('skip_reason', '')} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--providers", default="dry")
    parser.add_argument("--allow-online", action="store_true")
    parser.add_argument("--modes", default="plan,api,provider,cloud")
    parser.add_argument("--serve-url", default="http://127.0.0.1:8765")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="")
    parser.add_argument("--endpoint-model", default="gpt-5.3-codex-spark")
    parser.add_argument("--max-scenarios", type=int, default=0)
    parser.add_argument("--backend-max-scenarios", type=int, default=2)
    parser.add_argument("--backend-timeout-seconds", type=int, default=120)
    parser.add_argument("--backend-max-tokens", type=int, default=300)
    parser.add_argument("--out-root", default="C:/tmp/governed_agent_benchmark")
    args = parser.parse_args(argv)

    scenarios = default_scenarios()
    deterministic = run_governed_agent_benchmark(scenarios, max_scenarios=args.max_scenarios)
    backend_rows: list[dict[str, Any]] = []
    for provider in _split_csv(args.providers):
        backend, metadata = _backend_for_provider(provider, args)
        if backend is None:
            backend_rows.append(metadata)
            continue
        row = run_backend_benchmark(
            scenarios,
            backend,
            provider=provider,
            max_scenarios=args.backend_max_scenarios,
            timeout_seconds=args.backend_timeout_seconds,
            max_tokens=args.backend_max_tokens,
        )
        row.update(metadata)
        row["live"] = bool(metadata.get("live", False))
        row["operational"] = row["case_count"] > 0 and row["receipt_completeness"] > 0
        row["skipped"] = False
        backend_rows.append(row)

    run_root = Path(args.out_root).resolve() / datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    run_root.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "governed-agent-workflow-report/v1",
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "out_root": str(run_root),
        "config": {
            "providers": _split_csv(args.providers),
            "allow_online": args.allow_online,
            "endpoint_model": args.endpoint_model,
            "max_scenarios": args.max_scenarios,
            "backend_max_scenarios": args.backend_max_scenarios,
            "backend_timeout_seconds": args.backend_timeout_seconds,
        },
        "deterministic": deterministic,
        "backend_rows": backend_rows,
        "summary": {
            "deterministic_pass_rate": deterministic["metrics"]["pass_rate"],
            "backend_mean_pass_rate": round(
                sum(row.get("pass_rate", 0.0) for row in backend_rows if not row.get("skipped"))
                / max(1, sum(1 for row in backend_rows if not row.get("skipped"))),
                3,
            ),
            "backend_operational_rows": sum(1 for row in backend_rows if row.get("operational")),
            "backend_skipped_rows": sum(1 for row in backend_rows if row.get("skipped")),
        },
    }
    out_json = run_root / "governed_agent_benchmark.json"
    out_md = run_root / "governed_agent_benchmark.md"
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    out_md.write_text(render_markdown(report), encoding="utf-8")
    print(f"out_json={out_json}")
    print(f"out_md={out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
