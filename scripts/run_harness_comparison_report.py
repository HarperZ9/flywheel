"""Synthesize Codex-vs-Flywheel comparisons from existing scorecard artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402
from harness.provider_roles import provider_role as canonical_provider_role  # noqa: E402


SCHEMA = "harness.comparison-report/v1"


def now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def split_paths(value: str) -> list[Path]:
    return [Path(part.strip()) for part in value.split(";") if part.strip()]


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def load_json(path: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), ""
    except FileNotFoundError:
        return None, "missing_artifact"
    except (OSError, json.JSONDecodeError) as exc:
        return None, type(exc).__name__


def _provider_role(row: dict[str, Any]) -> str:
    return str(row.get("provider_role") or canonical_provider_role(str(row.get("provider", ""))))


def _metric_row(
    *,
    artifact_path: str,
    schema: str,
    benchmark_id: str,
    comparison_key: str,
    row: dict[str, Any],
    pass_rate: Any,
    quality_score: Any,
    latency_ms: Any,
    failure_class: Any,
) -> dict[str, Any]:
    provider = str(row.get("provider", ""))
    provider_role = _provider_role(row)
    return {
        "schema": "harness.comparison-report.metric-row/v1",
        "artifact_path": artifact_path,
        "artifact_schema": schema,
        "benchmark_id": benchmark_id,
        "comparison_key": comparison_key,
        "provider": provider,
        "provider_role": provider_role,
        "model_ref": str(row.get("model_ref", "")),
        "pass_rate": safe_float(pass_rate),
        "quality_score": safe_float(quality_score),
        "latency_ms": safe_float(latency_ms),
        "failure_class": str(failure_class or ""),
    }


def _m7_rows(data: dict[str, Any], path_text: str, *, benchmark_id: str) -> list[dict[str, Any]]:
    rows = data.get("backend_rows")
    if not isinstance(rows, list) and benchmark_id == "m7_source_mined":
        rows = data.get("rows")
    if not isinstance(rows, list):
        return []
    metric_rows = []
    for row in rows:
        if not isinstance(row, dict) or row.get("skipped"):
            continue
        quality = row.get("mean_quality_score", row.get("aggregate_metrics", {}).get("mean_quality_score", 0.0))
        metric_rows.append(_metric_row(
            artifact_path=path_text,
            schema=str(data.get("schema", "")),
            benchmark_id=benchmark_id,
            comparison_key=benchmark_id,
            row=row,
            pass_rate=row.get("pass_rate", 0.0),
            quality_score=quality,
            latency_ms=row.get("mean_latency_ms", 0.0),
            failure_class=row.get("failure_class", ""),
        ))
    return metric_rows


def _unisonai_rows(data: dict[str, Any], path_text: str) -> list[dict[str, Any]]:
    rows = data.get("rows") if isinstance(data.get("rows"), list) else []
    metric_rows = []
    for row in rows:
        if not isinstance(row, dict) or row.get("skipped"):
            continue
        metric_rows.append(_metric_row(
            artifact_path=path_text,
            schema=str(data.get("schema", "")),
            benchmark_id="unisonai_stateful_provider_matrix",
            comparison_key="unisonai_stateful_provider_matrix",
            row=row,
            pass_rate=row.get("pass_rate", 1.0 if row.get("passed") else 0.0),
            quality_score=row.get("quality_score", row.get("pass_rate", 1.0 if row.get("passed") else 0.0)),
            latency_ms=row.get("mean_latency_ms", row.get("latency_ms", 0.0)),
            failure_class=row.get("failure_class", ""),
        ))
    return metric_rows


def _classifier_rows(data: dict[str, Any], path_text: str) -> list[dict[str, Any]]:
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    rows = summary.get("rows") if isinstance(summary.get("rows"), list) else []
    metric_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        mode = str(row.get("mode", "unknown"))
        failure_class = ""
        if safe_float(row.get("error_rate")) > 0:
            failure_class = "provider_error"
        elif safe_float(row.get("unnecessary_refusal_rate")) > 0:
            failure_class = "unnecessary_refusal"
        metric_rows.append(_metric_row(
            artifact_path=path_text,
            schema=str(data.get("schema", "")),
            benchmark_id="classifier_friction_accountability",
            comparison_key=f"classifier_friction_accountability:{mode}",
            row=row,
            pass_rate=row.get("pass_rate", 0.0),
            quality_score=row.get("mean_quality_score", 0.0),
            latency_ms=row.get("mean_latency_ms", 0.0),
            failure_class=failure_class,
        ))
    return metric_rows


def _endpoint_gate_rows(data: dict[str, Any], path_text: str) -> list[dict[str, Any]]:
    rows = data.get("rows") if isinstance(data.get("rows"), list) else []
    metric_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        model = str(row.get("model", "unknown"))
        provider_row = {
            **row,
            "provider": row.get("provider", row.get("backend", "")),
        }
        metric_rows.append(_metric_row(
            artifact_path=path_text,
            schema=str(data.get("schema", "")),
            benchmark_id="local_model_endpoint_gate",
            comparison_key=f"local_model_endpoint_gate:{model}",
            row=provider_row,
            pass_rate=1.0 if row.get("generation_ok") else 0.0,
            quality_score=row.get("quality_score", 0.0),
            latency_ms=row.get("latency_ms", 0.0),
            failure_class=row.get("failure_class", ""),
        ))
    return metric_rows


def metric_rows_from_artifact(data: dict[str, Any], path_text: str) -> list[dict[str, Any]]:
    schema = str(data.get("schema", ""))
    if schema == "m7-source-mined-scorecard/v1":
        return _m7_rows(data, path_text, benchmark_id="m7_source_mined")
    if schema == "m7-governed-agent-scorecard/v1":
        return _m7_rows(data, path_text, benchmark_id="m7_governed_agent")
    if schema == "unisonai.stateful-provider-matrix/v1":
        return _unisonai_rows(data, path_text)
    if schema == "classifier-friction-benchmark/v1":
        return _classifier_rows(data, path_text)
    if schema == "harness.model-endpoint-gate/v1":
        return _endpoint_gate_rows(data, path_text)
    return []


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "rows": len(rows),
        "pass_rate": round(mean(row["pass_rate"] for row in rows), 4) if rows else 0.0,
        "quality_score": round(mean(row["quality_score"] for row in rows), 4) if rows else 0.0,
        "latency_ms": round(mean(row["latency_ms"] for row in rows), 3) if rows else 0.0,
        "failure_classes": sorted({str(row.get("failure_class", "")) for row in rows if row.get("failure_class")}),
        "artifact_paths": sorted({str(row.get("artifact_path", "")) for row in rows if row.get("artifact_path")}),
    }


def build_comparisons(
    metric_rows: list[dict[str, Any]],
    *,
    flywheel_role: str,
    codex_role: str,
) -> list[dict[str, Any]]:
    by_key: dict[str, list[dict[str, Any]]] = {}
    for row in metric_rows:
        by_key.setdefault(str(row["comparison_key"]), []).append(row)
    comparisons = []
    for key, rows in sorted(by_key.items()):
        by_provider: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_provider.setdefault(str(row["provider_role"]), []).append(row)
        flywheel = _aggregate(by_provider.get(flywheel_role, []))
        codex = _aggregate(by_provider.get(codex_role, []))
        available = bool(flywheel["rows"] and codex["rows"])
        benchmark_id = str(rows[0].get("benchmark_id", "")) if rows else ""
        comparison = {
            "schema": "harness.comparison-report.comparison/v1",
            "benchmark_id": benchmark_id,
            "comparison_key": key,
            "available": available,
            "flywheel_role": flywheel_role,
            "codex_role": codex_role,
            "flywheel": flywheel,
            "codex": codex,
            "observed_provider_roles": sorted(by_provider),
            "pass_rate_delta_flywheel_minus_codex": None,
            "quality_delta_flywheel_minus_codex": None,
            "latency_delta_ms_flywheel_minus_codex": None,
            "winner_by_quality": "insufficient_evidence",
        }
        if available:
            quality_delta = round(flywheel["quality_score"] - codex["quality_score"], 4)
            comparison.update({
                "pass_rate_delta_flywheel_minus_codex": round(flywheel["pass_rate"] - codex["pass_rate"], 4),
                "quality_delta_flywheel_minus_codex": quality_delta,
                "latency_delta_ms_flywheel_minus_codex": round(flywheel["latency_ms"] - codex["latency_ms"], 3),
                "winner_by_quality": "flywheel" if quality_delta > 0 else ("codex" if quality_delta < 0 else "tie"),
            })
        comparisons.append(comparison)
    return comparisons


def conclusion(comparisons: list[dict[str, Any]]) -> dict[str, Any]:
    available = [row for row in comparisons if row.get("available")]
    flywheel_wins = sum(1 for row in available if row.get("winner_by_quality") == "flywheel")
    codex_wins = sum(1 for row in available if row.get("winner_by_quality") == "codex")
    ties = sum(1 for row in available if row.get("winner_by_quality") == "tie")
    if not available:
        verdict = "COMPARISON_INSUFFICIENT"
        claim = "No artifact contained both flywheel and Codex provider-role evidence for the same comparison key."
    elif flywheel_wins > codex_wins:
        verdict = "FLYWHEEL_BETTER_ON_OBSERVED_SLICE"
        claim = "Flywheel has more quality wins than Codex on the observed shared comparison keys."
    elif codex_wins > flywheel_wins:
        verdict = "CODEX_BETTER_ON_OBSERVED_SLICE"
        claim = "Codex has more quality wins than Flywheel on the observed shared comparison keys."
    else:
        verdict = "MIXED_OR_TIED_ON_OBSERVED_SLICE"
        claim = "Observed shared comparison keys are tied or mixed; inspect per-benchmark deltas."
    return {
        "verdict": verdict,
        "claim": claim,
        "available_comparisons": len(available),
        "flywheel_quality_wins": flywheel_wins,
        "codex_quality_wins": codex_wins,
        "quality_ties": ties,
    }


def build_report(
    *,
    artifact_paths: list[Path],
    flywheel_role: str = "flywheel",
    codex_role: str = "codex",
) -> dict[str, Any]:
    metric_rows: list[dict[str, Any]] = []
    load_errors: list[dict[str, str]] = []
    loaded_artifacts: list[dict[str, Any]] = []
    for path in artifact_paths:
        data, error = load_json(path)
        if data is None:
            load_errors.append({"artifact_path": str(path), "error": error})
            continue
        rows = metric_rows_from_artifact(data, str(path))
        loaded_artifacts.append({
            "artifact_path": str(path),
            "schema": data.get("schema", ""),
            "metric_rows": len(rows),
            "recognized": bool(rows),
        })
        metric_rows.extend(rows)
    comparisons = build_comparisons(metric_rows, flywheel_role=flywheel_role, codex_role=codex_role)
    summary = {
        "artifact_paths": len(artifact_paths),
        "loaded_artifacts": len(loaded_artifacts),
        "load_errors": len(load_errors),
        "recognized_artifacts": sum(1 for row in loaded_artifacts if row["recognized"]),
        "metric_rows": len(metric_rows),
        "comparison_keys": len(comparisons),
        "available_codex_flywheel_comparisons": sum(1 for row in comparisons if row.get("available")),
        "provider_roles_observed": sorted({str(row.get("provider_role", "")) for row in metric_rows if row.get("provider_role")}),
        "benchmark_ids_observed": sorted({str(row.get("benchmark_id", "")) for row in metric_rows if row.get("benchmark_id")}),
    }
    report_conclusion = conclusion(comparisons)
    return {
        "schema": SCHEMA,
        "timestamp_utc": now_utc(),
        "flywheel_role": flywheel_role,
        "codex_role": codex_role,
        "loaded_artifacts": loaded_artifacts,
        "load_errors": load_errors,
        "metric_rows": metric_rows,
        "comparisons": comparisons,
        "summary": {**summary, **report_conclusion},
        "conclusion": report_conclusion,
        "limitations": [
            "This report compares existing scorecard artifacts only; it does not execute or validate benchmarks.",
            "A missing provider row is treated as missing evidence, not as a model-quality failure.",
            "Cross-benchmark aggregation counts comparison keys equally; inspect raw deltas before making release claims.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Harness comparison report",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Timestamp UTC: `{report['timestamp_utc']}`",
        f"- Verdict: `{report['conclusion']['verdict']}`",
        f"- Claim: {report['conclusion']['claim']}",
        f"- Loaded artifacts: `{summary['loaded_artifacts']}` / `{summary['artifact_paths']}`",
        f"- Recognized artifacts: `{summary['recognized_artifacts']}`",
        f"- Metric rows: `{summary['metric_rows']}`",
        f"- Available Codex/Flywheel comparisons: `{summary['available_codex_flywheel_comparisons']}`",
        f"- Flywheel quality wins: `{summary['flywheel_quality_wins']}`",
        f"- Codex quality wins: `{summary['codex_quality_wins']}`",
        f"- Quality ties: `{summary['quality_ties']}`",
        "",
        "| Benchmark | Key | Available | Pass delta | Quality delta | Latency delta ms | Winner | Providers |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ]
    for row in report["comparisons"]:
        lines.append(
            "| {benchmark} | {key} | {available} | {pass_delta} | {quality_delta} | {latency_delta} | {winner} | {providers} |".format(
                benchmark=row.get("benchmark_id", ""),
                key=row.get("comparison_key", ""),
                available=str(row.get("available", False)).lower(),
                pass_delta="" if row.get("pass_rate_delta_flywheel_minus_codex") is None else row.get("pass_rate_delta_flywheel_minus_codex"),
                quality_delta="" if row.get("quality_delta_flywheel_minus_codex") is None else row.get("quality_delta_flywheel_minus_codex"),
                latency_delta="" if row.get("latency_delta_ms_flywheel_minus_codex") is None else row.get("latency_delta_ms_flywheel_minus_codex"),
                winner=row.get("winner_by_quality", ""),
                providers=", ".join(row.get("observed_provider_roles", [])),
            )
        )
    if report["load_errors"]:
        lines.extend(["", "## Load errors", "", "| Artifact | Error |", "|---|---|"])
        for row in report["load_errors"]:
            lines.append(f"| {row.get('artifact_path', '')} | {row.get('error', '')} |")
    lines.extend(["", "## Limitations", ""])
    for item in report["limitations"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def write_text(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def store_report(report: dict[str, Any], *, store_root: str, run_id: str, artifacts: list[tuple[str, str]]) -> list[dict[str, Any]]:
    if not store_root:
        return []
    store = FileBackedHarnessStore(Path(store_root))
    outputs = [
        store.put_receipt(
            kind="harness_comparison_report",
            body=report,
            run_id=run_id,
            verdict=report["conclusion"]["verdict"],
        )
    ]
    for path_text, label in artifacts:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", default="")
    parser.add_argument("--flywheel-role", default="flywheel")
    parser.add_argument("--codex-role", default="codex")
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    report = build_report(
        artifact_paths=split_paths(args.artifacts),
        flywheel_role=args.flywheel_role,
        codex_role=args.codex_role,
    )
    json_text = json.dumps(report, indent=2, sort_keys=True)
    md_text = render_markdown(report)
    json_path = write_text(args.out, json_text)
    md_path = write_text(args.markdown_out, md_text)
    store_outputs = store_report(
        report,
        store_root=args.store_root,
        run_id=args.run_id,
        artifacts=[
            (json_path, "harness-comparison-report-json"),
            (md_path, "harness-comparison-report-markdown"),
        ],
    )
    if store_outputs:
        report = {**report, "store_outputs": store_outputs}
        json_text = json.dumps(report, indent=2, sort_keys=True)
        write_text(args.out, json_text)
    print(json_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
