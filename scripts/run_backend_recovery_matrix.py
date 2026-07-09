"""Run backend-recovery benchmark matrix across configured provider selectors."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.run_flywheel_integration_benchmark import (  # noqa: E402
    RecoveryPolicy,
    _split_csv,
    run_selected_backend_recovery,
)


DEFAULT_PROVIDERS = "dry,serve,ollama,codex,claude,opencode"
ONLINE_PROVIDERS = {"codex", "claude", "opencode", "open-code"}


def _skip_online(provider: str) -> dict[str, Any]:
    return {
        "schema": "agent.backend-recovery-benchmark/v1",
        "adapter": "chat-backend",
        "provider": provider,
        "live": False,
        "operational": False,
        "skipped": True,
        "skip_reason": "online provider skipped; pass --allow-online to run CLI/API backends",
        "backend_name": "",
        "scenario_count": 0,
        "metrics": {
            "recovery_success_rate": 0.0,
            "silent_failure_rate": 0.0,
            "retry_budget_compliance": 0.0,
            "fallback_quality": 0.0,
            "receipt_completeness": 0.0,
            "p95_recovery_latency": 0,
        },
        "results": [],
    }


def run_matrix(args: argparse.Namespace) -> dict[str, Any]:
    providers = _split_csv(args.providers)
    modes = tuple(_split_csv(args.modes)) or ("plan", "api", "provider", "cloud")
    policy = RecoveryPolicy(
        retry_budget=args.retry_budget,
        fallback_enabled=not args.disable_fallback,
        stale_recompute_enabled=not args.disable_stale_recompute,
        typed_escalation_enabled=not args.disable_typed_escalation,
    )
    rows = []
    for provider in providers:
        normalized = provider.lower().strip()
        if normalized in ONLINE_PROVIDERS and not args.allow_online:
            rows.append(_skip_online(normalized))
            continue
        rows.append(
            run_selected_backend_recovery(
                provider=normalized,
                serve_url=args.serve_url,
                ollama_url=args.ollama_url,
                model=args.model,
                modes=modes,
                max_scenarios=args.max_scenarios,
                policy=policy,
            )
        )

    live_rows = [row for row in rows if row.get("live") and not row.get("skipped")]
    operational_rows = [row for row in rows if row.get("operational")]
    runnable_rows = [row for row in rows if not row.get("skipped")]
    total_scenarios = sum(row.get("scenario_count", 0) for row in runnable_rows)
    fault_coverage = sorted({
        fault for row in runnable_rows for fault in row["metrics"].get("fault_coverage", [])
    })
    return {
        "schema": "agent.backend-recovery-matrix/v1",
        "timestamp_utc": datetime.utcnow().isoformat() + "Z",
        "providers_requested": providers,
        "modes": list(modes),
        "allow_online": bool(args.allow_online),
        "max_scenarios": args.max_scenarios,
        "policy": {
            "retry_budget": policy.retry_budget,
            "fallback_enabled": policy.fallback_enabled,
            "stale_recompute_enabled": policy.stale_recompute_enabled,
            "typed_escalation_enabled": policy.typed_escalation_enabled,
        },
        "rows": rows,
        "summary": {
            "providers": len(rows),
            "runnable": len(runnable_rows),
            "live": len(live_rows),
            "operational": len(operational_rows),
            "skipped": sum(1 for row in rows if row.get("skipped")),
            "total_scenarios": total_scenarios,
            "total_failures": sum(
                row["metrics"].get("scenario_fail_count", 0) for row in runnable_rows
            ),
            "fault_coverage": fault_coverage,
            "mean_recovery_success_rate": (
                round(
                    sum(row["metrics"]["recovery_success_rate"] for row in runnable_rows)
                    / len(runnable_rows),
                    3,
                )
                if runnable_rows
                else 0.0
            ),
            "mean_receipt_completeness": (
                round(
                    sum(row["metrics"]["receipt_completeness"] for row in runnable_rows)
                    / len(runnable_rows),
                    3,
                )
                if runnable_rows
                else 0.0
            ),
            "silent_failure_rows": sum(
                1 for row in runnable_rows if row["metrics"]["silent_failure_rate"] > 0
            ),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Backend Recovery Matrix",
        "",
        f"- timestamp_utc: {report['timestamp_utc']}",
        f"- allow_online: {report['allow_online']}",
        f"- max_scenarios: {report['max_scenarios']}",
        f"- retry_budget: {report['policy']['retry_budget']}",
        f"- fallback_enabled: {report['policy']['fallback_enabled']}",
        f"- stale_recompute_enabled: {report['policy']['stale_recompute_enabled']}",
        f"- typed_escalation_enabled: {report['policy']['typed_escalation_enabled']}",
        "",
        "## Summary",
        "",
        f"- providers: {report['summary']['providers']}",
        f"- runnable: {report['summary']['runnable']}",
        f"- live: {report['summary']['live']}",
        f"- operational: {report['summary']['operational']}",
        f"- skipped: {report['summary']['skipped']}",
        f"- total_scenarios: {report['summary']['total_scenarios']}",
        f"- total_failures: {report['summary']['total_failures']}",
        f"- fault_coverage: {', '.join(report['summary']['fault_coverage'])}",
        f"- mean_recovery_success_rate: {report['summary']['mean_recovery_success_rate']}",
        f"- mean_receipt_completeness: {report['summary']['mean_receipt_completeness']}",
        f"- silent_failure_rows: {report['summary']['silent_failure_rows']}",
        "",
        "## Providers",
        "",
        "| Provider | Backend | Live | Operational | Skipped | Scenarios | Pass | Fail | Recovery | Retry | Fallback | Escalation | p95 ms | Receipts | Reason |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["rows"]:
        metrics = row["metrics"]
        lines.append(
            "| "
            f"{row.get('provider')} | "
            f"{row.get('backend_name', '')} | "
            f"{row.get('live')} | "
            f"{row.get('operational')} | "
            f"{row.get('skipped')} | "
            f"{row.get('scenario_count')} | "
            f"{metrics.get('scenario_pass_count')} | "
            f"{metrics.get('scenario_fail_count')} | "
            f"{metrics.get('recovery_success_rate')} | "
            f"{metrics.get('retry_use_rate')} | "
            f"{metrics.get('fallback_use_rate')} | "
            f"{metrics.get('typed_escalation_rate')} | "
            f"{metrics.get('p95_recovery_latency')} | "
            f"{metrics.get('receipt_completeness')} | "
            f"{row.get('skip_reason', '')} |"
        )
    lines.extend(["", "## Per-fault metrics", ""])
    for row in report["rows"]:
        per_fault = row["metrics"].get("per_fault", {})
        if not per_fault:
            continue
        lines.append(f"### {row.get('provider')}")
        lines.append("")
        lines.append("| Fault | Scenarios | Pass rate | Retry | Fallback | Escalation | p95 ms |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for fault, metrics in per_fault.items():
            lines.append(
                "| "
                f"{fault} | "
                f"{metrics.get('scenarios')} | "
                f"{metrics.get('pass_rate')} | "
                f"{metrics.get('retry_use_rate')} | "
                f"{metrics.get('fallback_use_rate')} | "
                f"{metrics.get('typed_escalation_rate')} | "
                f"{metrics.get('p95_latency_ms')} |"
            )
        lines.append("")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--providers", default=DEFAULT_PROVIDERS)
    parser.add_argument("--modes", default="plan,api,provider,cloud")
    parser.add_argument("--serve-url", default="http://127.0.0.1:8765")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="")
    parser.add_argument("--max-scenarios", type=int, default=1)
    parser.add_argument("--retry-budget", type=int, default=2)
    parser.add_argument("--disable-fallback", action="store_true")
    parser.add_argument("--disable-stale-recompute", action="store_true")
    parser.add_argument("--disable-typed-escalation", action="store_true")
    parser.add_argument("--allow-online", action="store_true")
    parser.add_argument("--out-root", default="C:/tmp/backend_recovery_matrix")
    args = parser.parse_args()

    out_root = Path(args.out_root)
    run_root = out_root / datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    run_root.mkdir(parents=True, exist_ok=True)
    report = run_matrix(args)
    report["out_root"] = str(run_root)
    out_json = run_root / "backend_recovery_matrix.json"
    out_md = run_root / "backend_recovery_matrix.md"
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    out_md.write_text(render_markdown(report), encoding="utf-8")
    print(f"out_json={out_json}")
    print(f"out_md={out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
