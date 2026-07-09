"""Zero-dependency front controller for the local Codex/Flywheel harness."""

from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore


DEFAULT_STORE_ROOT = "C:/tmp/harness_file_store"
DEFAULT_SEED_DIR = "C:/tmp/harness_closed_loop_seed"
LOCAL_MODEL_VENV_PYTHON = "E:/local-model-run/venv/Scripts/python.exe"


def _default_serve_python() -> str:
    explicit = os.environ.get("LOCAL_SERVE_PYTHON", "").strip()
    if explicit:
        return explicit
    if Path(LOCAL_MODEL_VENV_PYTHON).exists():
        return LOCAL_MODEL_VENV_PYTHON
    return sys.executable


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _add_common_io(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--store-root", default=DEFAULT_STORE_ROOT)
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--run-id", default="")


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def build_manifest(*, store_root: str = DEFAULT_STORE_ROOT) -> dict:
    return {
        "schema": "harness.executable-manifest/v1",
        "timestamp_utc": _now(),
        "entrypoint": "harness.cmd",
        "dispatcher": "scripts/run_harness_cli.py",
        "store_root_default": store_root,
        "dependency_posture": "python-stdlib plus existing harness modules; no package build required",
        "commands": [
            {
                "name": "manifest",
                "delegates_to": "scripts/run_harness_cli.py",
                "purpose": "Emit this executable-surface manifest as JSON/Markdown and optional receipt.",
                "schemas": ["harness.executable-manifest/v1"],
                "evidence_surface": "front-controller command registry",
                "default_artifacts": [
                    "C:/tmp/harness_executable_manifest.json",
                    "C:/tmp/harness_executable_manifest.md",
                ],
                "long_running_risk": "low",
                "recommended_validation_slice": "python -m pytest tests/test_harness_cli.py -q",
            },
            {
                "name": "registry",
                "delegates_to": "scripts/run_harness_cli.py",
                "purpose": "Emit a static local HTML command registry generated from the executable manifest.",
                "schemas": ["harness.command-registry-html/v1"],
                "evidence_surface": "human-readable command/risk/artifact registry",
                "default_artifacts": [
                    "C:/tmp/harness_command_registry.html",
                    "C:/tmp/harness_command_registry.json",
                ],
                "long_running_risk": "low",
                "recommended_validation_slice": "python -m pytest tests/test_harness_cli.py -q",
            },
            {
                "name": "benchmarks",
                "delegates_to": "scripts/run_benchmark_profile_manifest.py",
                "purpose": "Emit the weighted benchmark profile manifest and metadata-only existing artifact inventory.",
                "schemas": ["harness.benchmark-profile-manifest/v1"],
                "evidence_surface": "benchmark suite definitions, metric weights, provider matrix, and artifact inventory",
                "default_artifacts": [
                    "C:/tmp/harness_benchmark_profile_manifest.json",
                    "C:/tmp/harness_benchmark_profile_manifest.md",
                ],
                "long_running_risk": "low",
                "recommended_validation_slice": "python -m pytest tests/test_benchmark_profile_manifest.py tests/test_harness_cli.py -q",
            },
            {
                "name": "forum-route",
                "delegates_to": "scripts/run_forum_route_receipts.py",
                "purpose": "Emit metadata-only Forum route prompt hashes and optional observed route-frame metadata.",
                "schemas": ["harness.forum-route-receipts/v1"],
                "evidence_surface": "route prompt hashes, observed route confidence, escalation state, domain, intent, posture, and proof lane",
                "default_artifacts": [
                    "C:/tmp/forum_route_receipts.json",
                    "C:/tmp/forum_route_receipts.md",
                ],
                "long_running_risk": "low",
                "recommended_validation_slice": "python -m pytest tests/test_forum_route_receipts.py tests/test_harness_cli.py -q",
            },
            {
                "name": "mcp-health",
                "delegates_to": "scripts/run_mcp_tool_health_receipts.py",
                "purpose": "Emit metadata-only MCP/tool root posture and optional non-secret live status observations.",
                "schemas": ["harness.mcp-tool-health/v1"],
                "evidence_surface": "configured tool roots plus observed healthy/degraded/unobserved/missing-root posture",
                "default_artifacts": [
                    "C:/tmp/mcp_tool_health.json",
                    "C:/tmp/mcp_tool_health.md",
                ],
                "long_running_risk": "low",
                "recommended_validation_slice": "python -m pytest tests/test_mcp_tool_health_receipts.py tests/test_harness_cli.py -q",
            },
            {
                "name": "benchmark-coverage",
                "delegates_to": "scripts/run_benchmark_profile_coverage.py",
                "purpose": "Compare the weighted benchmark profile against observed scorecard artifacts and flag missing coverage.",
                "schemas": ["harness.benchmark-profile-coverage/v1"],
                "evidence_surface": "declared-vs-observed benchmark/provider coverage report",
                "default_artifacts": [
                    "C:/tmp/harness_benchmark_profile_coverage.json",
                    "C:/tmp/harness_benchmark_profile_coverage.md",
                ],
                "long_running_risk": "low",
                "recommended_validation_slice": "python -m pytest tests/test_benchmark_profile_coverage.py tests/test_harness_cli.py -q",
            },
            {
                "name": "comparison",
                "delegates_to": "scripts/run_harness_comparison_report.py",
                "purpose": "Synthesize Codex-vs-Flywheel deltas from existing scorecard artifacts.",
                "schemas": ["harness.comparison-report/v1"],
                "evidence_surface": "artifact-ingested provider-role comparison rows and Flywheel-minus-Codex deltas",
                "default_artifacts": [
                    "C:/tmp/harness_comparison_report.json",
                    "C:/tmp/harness_comparison_report.md",
                ],
                "long_running_risk": "low",
                "recommended_validation_slice": "python -m pytest tests/test_harness_comparison_report.py tests/test_harness_cli.py -q",
            },
            {
                "name": "execution-matrix",
                "delegates_to": "scripts/run_benchmark_execution_matrix.py",
                "purpose": "Emit non-executing benchmark tiers, commands, artifacts, schemas, and evidence gates.",
                "schemas": ["harness.benchmark-execution-matrix/v1"],
                "evidence_surface": "dry/focused/full run matrix with provider roles, approval gates, artifact paths, and expected schemas",
                "default_artifacts": [
                    "C:/tmp/benchmark_execution_matrix_20260709.json",
                    "C:/tmp/benchmark_execution_matrix_20260709.md",
                ],
                "long_running_risk": "low",
                "recommended_validation_slice": "python -m pytest tests/test_benchmark_execution_matrix.py tests/test_harness_cli.py -q",
            },
            {
                "name": "schematic-drift",
                "delegates_to": "scripts/run_schematic_drift_check.py",
                "purpose": "Check closed-loop graph and schematic report for metadata-only drift.",
                "schemas": ["harness.schematic-drift-check/v1"],
                "evidence_surface": "missing schematic nodes, edges, files, and stale prose markers",
                "default_artifacts": [
                    "C:/tmp/schematic_drift_check.json",
                    "C:/tmp/schematic_drift_check.md",
                ],
                "long_running_risk": "low",
                "recommended_validation_slice": "python -m pytest tests/test_schematic_drift_check.py tests/test_harness_cli.py -q",
            },
            {
                "name": "agentic-tasks",
                "delegates_to": "scripts/run_agentic_task_set_manifest.py",
                "purpose": "Expand the custom agentic task set into prompt hashes, planned artifacts, and manifest-only dry scorecard rows.",
                "schemas": ["harness.agentic-task-manifest/v1", "harness.agentic-task-scorecard/v1"],
                "evidence_surface": "non-executing custom agentic benchmark task manifest",
                "default_artifacts": [
                    "C:/tmp/agentic_task_manifest.json",
                    "C:/tmp/agentic_task_manifest.md",
                ],
                "long_running_risk": "low",
                "recommended_validation_slice": "python -m pytest tests/test_agentic_task_set_manifest.py tests/test_harness_cli.py -q",
            },
            {
                "name": "cross-harness",
                "delegates_to": "scripts/run_cross_harness_manifest.py",
                "purpose": "Expand the cross-harness adapter contract into same-task prompt hashes and provider-role planned receipt rows.",
                "schemas": ["harness.cross-harness-manifest/v1", "harness.cross-harness-task-scorecard/v1"],
                "evidence_surface": "non-executing Codex/Flywheel/Claude/OpenCode/local-model comparability manifest",
                "default_artifacts": [
                    "C:/tmp/cross_harness_manifest.json",
                    "C:/tmp/cross_harness_manifest.md",
                ],
                "long_running_risk": "low",
                "recommended_validation_slice": "python -m pytest tests/test_cross_harness_manifest.py tests/test_harness_cli.py -q",
            },
            {
                "name": "adapter-runtime",
                "delegates_to": "scripts/run_adapter_runtime_matrix.py",
                "purpose": "Emit metadata-only adapter/runtime compatibility across Codex, Flywheel, Claude Code, OpenCode, and local endpoints.",
                "schemas": ["harness.adapter-runtime-matrix/v1"],
                "evidence_surface": "contract roles joined with optional endpoint-profile and endpoint-auth metadata",
                "default_artifacts": [
                    "C:/tmp/adapter_runtime_matrix.json",
                    "C:/tmp/adapter_runtime_matrix.md",
                ],
                "long_running_risk": "low",
                "recommended_validation_slice": "python -m pytest tests/test_adapter_runtime_matrix.py tests/test_harness_cli.py -q",
            },
            {
                "name": "embodied-realtime",
                "delegates_to": "scripts/run_embodied_realtime_multimodal_plan.py",
                "purpose": "Emit a metadata-only embodied realtime multimodal benchmark plan from the Boris/ENBSeries feedback contract.",
                "schemas": ["harness.embodied-realtime-multimodal/v1"],
                "evidence_surface": "non-executing robotics latency, sensor grounding, code-drawing, multimodal, and affective-drift probe plan",
                "default_artifacts": [
                    "C:/tmp/embodied_realtime_multimodal_plan.json",
                    "C:/tmp/embodied_realtime_multimodal_plan.md",
                ],
                "long_running_risk": "low",
                "recommended_validation_slice": "python -m pytest tests/test_embodied_realtime_multimodal_plan.py tests/test_harness_cli.py -q",
            },
            {
                "name": "model-card-claims",
                "delegates_to": "scripts/run_model_card_claim_table.py",
                "purpose": "Emit a non-executing model-card claim table for benchmark model leads before result claims.",
                "schemas": ["harness.model-card-claim-table/v1"],
                "evidence_surface": "candidate model identity, source URL, license, modality, provenance, and local-execution claim status",
                "default_artifacts": [
                    "C:/tmp/model_card_claim_table.json",
                    "C:/tmp/model_card_claim_table.md",
                ],
                "long_running_risk": "low",
                "recommended_validation_slice": "python -m pytest tests/test_model_card_claim_table.py tests/test_harness_cli.py -q",
            },
            {
                "name": "tool-hardening",
                "delegates_to": "scripts/run_tool_hardening_plan.py",
                "purpose": "Generate an enterprise hardening action plan from a tool-readiness receipt.",
                "schemas": ["harness.tool-hardening-plan/v1"],
                "evidence_surface": "observed readiness gaps converted into prioritized actions and release gates",
                "default_artifacts": [
                    "C:/tmp/tool_hardening_plan_20260709.json",
                    "C:/tmp/tool_hardening_plan_20260709.md",
                ],
                "long_running_risk": "low",
                "recommended_validation_slice": "python -m pytest tests/test_tool_hardening_plan.py tests/test_harness_cli.py -q",
            },
            {
                "name": "classifier-friction",
                "delegates_to": "scripts/run_classifier_friction_benchmark.py",
                "purpose": "Run prompt-layer guardrail/accountability friction benchmark across selected providers.",
                "schemas": ["classifier-friction-benchmark/v1"],
                "evidence_surface": "provider x mode x task quality, refusal, latency, receipt, and friction deltas",
                "default_artifacts": [
                    "C:/tmp/classifier_friction_benchmark.json",
                    "C:/tmp/classifier_friction_benchmark.md",
                ],
                "long_running_risk": "medium",
                "recommended_validation_slice": "python -m pytest tests/test_classifier_friction_benchmark.py tests/test_harness_cli.py -q",
            },
            {
                "name": "endpoint-gate",
                "delegates_to": "scripts/run_model_endpoint_gate.py",
                "purpose": "Run bounded live health/generation gates against local model endpoint profiles.",
                "schemas": ["harness.model-endpoint-gate/v1"],
                "evidence_surface": "local 14B/32B endpoint health and fixed generation rows",
                "default_artifacts": [
                    "C:/tmp/model_endpoint_gate_20260709.json",
                    "C:/tmp/model_endpoint_gate_20260709.md",
                ],
                "long_running_risk": "medium",
                "recommended_validation_slice": "python -m pytest tests/test_model_endpoint_gate.py tests/test_harness_cli.py -q",
            },
            {
                "name": "endpoint-launch-readiness",
                "delegates_to": "scripts/run_local_model_launch_readiness.py",
                "purpose": "Emit non-destructive local model serve launch readiness and port-owner diagnostics from endpoint profiles.",
                "schemas": ["harness.local-model-launch-readiness/v1"],
                "evidence_surface": "model root presence, endpoint port ownership, wrong-service conflicts, and launch command templates",
                "default_artifacts": [
                    "C:/tmp/local_model_launch_readiness_20260709.json",
                    "C:/tmp/local_model_launch_readiness_20260709.md",
                ],
                "long_running_risk": "low",
                "recommended_validation_slice": "python -m pytest tests/test_local_model_launch_readiness.py tests/test_harness_cli.py -q",
            },
            {
                "name": "serve-launch",
                "delegates_to": "scripts/run_local_model_serve_launcher.py",
                "purpose": "Plan or start local harness/serve.py processes from endpoint profiles with receipt-backed PID, log, and health status.",
                "schemas": ["harness.local-model-serve-launch/v1"],
                "evidence_surface": "serve launch commands, optional process IDs, log paths, and bounded health-poll status",
                "default_artifacts": [
                    "C:/tmp/local_model_serve_launch_20260709.json",
                    "C:/tmp/local_model_serve_launch_20260709.md",
                ],
                "long_running_risk": "medium",
                "recommended_validation_slice": "python -m pytest tests/test_local_model_serve_launcher.py tests/test_harness_cli.py -q",
            },
            {
                "name": "serve-resource",
                "delegates_to": "scripts/run_local_model_resource_preflight.py",
                "purpose": "Emit GPU resource preflight before local harness/serve.py launch attempts.",
                "schemas": ["harness.local-model-resource-preflight/v1"],
                "evidence_surface": "GPU free/used memory, calibrated 14B/32B VRAM estimates, and launch resource verdicts",
                "default_artifacts": [
                    "C:/tmp/local_model_resource_preflight_20260709.json",
                    "C:/tmp/local_model_resource_preflight_20260709.md",
                ],
                "long_running_risk": "low",
                "recommended_validation_slice": "python -m pytest tests/test_local_model_resource_preflight.py tests/test_harness_cli.py -q",
            },
            {
                "name": "model-publish",
                "delegates_to": "scripts/run_model_publish_plan.py",
                "purpose": "Generate 14B/32B candidate names and publication blockers from release-readiness evidence.",
                "schemas": ["harness.model-publish-plan/v1"],
                "evidence_surface": "model release gates, candidate names, required artifacts, blockers, and do-not-publish status",
                "default_artifacts": [
                    "C:/tmp/model_publish_plan_20260709.json",
                    "C:/tmp/model_publish_plan_20260709.md",
                ],
                "long_running_risk": "low",
                "recommended_validation_slice": "python -m pytest tests/test_model_publish_plan.py tests/test_harness_cli.py -q",
            },
            {
                "name": "plan",
                "delegates_to": "scripts/run_closed_loop_benchmark_seed.py --dry-plan",
                "purpose": "Emit closed-loop seed dry plan without executing benchmark/provider steps.",
                "schemas": ["harness.closed-loop-benchmark-seed/v1"],
                "evidence_surface": "planned commands",
                "default_artifacts": ["C:/tmp/harness_closed_loop_seed_plan.json"],
                "long_running_risk": "low",
                "recommended_validation_slice": "python -m pytest tests/test_closed_loop_benchmark_seed.py -q",
            },
            {
                "name": "seed",
                "delegates_to": "scripts/run_closed_loop_benchmark_seed.py",
                "purpose": "Execute the current closed-loop seed receipt bundle.",
                "schemas": ["harness.closed-loop-benchmark-seed/v1"],
                "evidence_surface": "run/events/receipts/artifacts",
                "default_artifacts": [
                    "C:/tmp/harness_closed_loop_seed.json",
                    "C:/tmp/harness_closed_loop_seed",
                ],
                "long_running_risk": "high",
                "recommended_validation_slice": "python -m pytest tests/test_closed_loop_benchmark_seed.py tests/test_receipt_store_sinks.py -q",
            },
            {
                "name": "outcome",
                "delegates_to": "scripts/run_closed_loop_outcome_report.py",
                "purpose": "Synthesize a seed report or stored run into outcome JSON/Markdown.",
                "schemas": ["harness.closed-loop-outcome/v1"],
                "evidence_surface": "parsed child artifacts and outcome receipt",
                "default_artifacts": [
                    "C:/tmp/harness_closed_loop_outcome.json",
                    "C:/tmp/harness_closed_loop_outcome.md",
                ],
                "long_running_risk": "low",
                "recommended_validation_slice": "python -m pytest tests/test_closed_loop_outcome_report.py -q",
            },
            {
                "name": "query",
                "delegates_to": "scripts/run_harness_store_query.py",
                "purpose": "Query the zero-dependency file-backed harness store.",
                "schemas": ["harness.file-store-query/v1"],
                "evidence_surface": "runs/events/receipts/artifacts JSONL",
                "default_artifacts": [
                    "C:/tmp/harness_file_store_query.json",
                    "C:/tmp/harness_file_store_query.md",
                ],
                "long_running_risk": "low",
                "recommended_validation_slice": "python -m pytest tests/test_harness_store_query.py -q",
            },
            {
                "name": "readiness",
                "delegates_to": "metadata-only readiness/profile scripts",
                "purpose": "Emit one metadata-only preflight receipt.",
                "targets": ["context", "tools", "model-endpoints", "model-release", "gather", "endpoint-auth", "pubscan"],
                "schemas": [
                    "harness.context-inventory/v1",
                    "harness.tool-readiness/v1",
                    "harness.model-endpoint-profiles/v1",
                    "harness.model-release-readiness/v1",
                    "harness.gather-readiness/v1",
                    "harness.endpoint-auth-status/v1",
                    "harness.pubscan-resource-profiles/v1",
                ],
                "evidence_surface": "metadata-only readiness receipts",
                "default_artifacts": [
                    "C:/tmp/context_inventory_20260709.json",
                    "C:/tmp/tool_readiness_20260709.json",
                    "C:/tmp/model_endpoint_profiles_20260709.json",
                    "C:/tmp/model_release_readiness_20260709.json",
                    "C:/tmp/gather_readiness_20260709.json",
                    "C:/tmp/harness_endpoint_auth_status_20260709.json",
                    "C:/tmp/pubscan_resource_profiles_20260709.json",
                ],
                "long_running_risk": "low",
                "recommended_validation_slice": "python -m pytest tests/test_context_inventory.py tests/test_tool_readiness_receipts.py tests/test_model_endpoint_profiles.py tests/test_model_release_readiness.py tests/test_gather_readiness.py tests/test_receipt_store_sinks.py -q",
            },
        ],
    }


def render_manifest_markdown(manifest: dict) -> str:
    lines = [
        "# Harness executable manifest",
        "",
        f"- Schema: `{manifest['schema']}`",
        f"- Timestamp UTC: `{manifest['timestamp_utc']}`",
        f"- Entrypoint: `{manifest['entrypoint']}`",
        f"- Dispatcher: `{manifest['dispatcher']}`",
        f"- Store root default: `{manifest['store_root_default']}`",
        f"- Dependency posture: {manifest['dependency_posture']}",
        "",
        "| Command | Delegates to | Risk | Default artifacts | Schemas | Evidence surface |",
        "|---|---|---|---:|---|---|",
    ]
    for row in manifest["commands"]:
        schemas = ", ".join(row.get("schemas", []))
        lines.append(
            "| {name} | {delegate} | {risk} | {artifact_count} | {schemas} | {evidence} |".format(
                name=row.get("name", ""),
                delegate=row.get("delegates_to", ""),
                risk=row.get("long_running_risk", ""),
                artifact_count=len(row.get("default_artifacts", []) or []),
                schemas=schemas,
                evidence=row.get("evidence_surface", ""),
            )
        )
    return "\n".join(lines) + "\n"


def _esc(value) -> str:
    return html.escape(str(value), quote=True)


def render_registry_html(manifest: dict) -> str:
    grouped = {"low": [], "medium": [], "high": []}
    for row in manifest["commands"]:
        risk = str(row.get("long_running_risk", "low"))
        grouped.setdefault(risk, []).append(row)

    cards: list[str] = []
    for risk in ("high", "medium", "low"):
        rows = grouped.get(risk, [])
        if not rows:
            continue
        cards.append(f'<section class="risk-block risk-{_esc(risk)}">')
        cards.append(f'<h2>{_esc(risk)} risk</h2>')
        cards.append('<div class="command-grid">')
        for row in rows:
            artifacts = "".join(f"<li>{_esc(item)}</li>" for item in row.get("default_artifacts", []))
            schemas = "".join(f"<li>{_esc(item)}</li>" for item in row.get("schemas", []))
            targets = row.get("targets", [])
            target_text = ", ".join(str(item) for item in targets) if targets else "none"
            cards.append(
                """
                <article class="command-card">
                  <div class="card-topline">
                    <span class="command-name">{name}</span>
                    <span class="risk-pill">{risk}</span>
                  </div>
                  <p class="purpose">{purpose}</p>
                  <dl>
                    <dt>Delegates</dt><dd>{delegate}</dd>
                    <dt>Evidence</dt><dd>{evidence}</dd>
                    <dt>Targets</dt><dd>{targets}</dd>
                    <dt>Validation</dt><dd>{validation}</dd>
                  </dl>
                  <div class="lists">
                    <div><h3>Artifacts</h3><ul>{artifacts}</ul></div>
                    <div><h3>Schemas</h3><ul>{schemas}</ul></div>
                  </div>
                </article>
                """.format(
                    name=_esc(row.get("name", "")),
                    risk=_esc(risk),
                    purpose=_esc(row.get("purpose", "")),
                    delegate=_esc(row.get("delegates_to", "")),
                    evidence=_esc(row.get("evidence_surface", "")),
                    targets=_esc(target_text),
                    validation=_esc(row.get("recommended_validation_slice", "")),
                    artifacts=artifacts or "<li>none</li>",
                    schemas=schemas or "<li>none</li>",
                )
            )
        cards.append("</div></section>")

    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Harness command registry</title>
  <style>
    :root {
      --paper: #f7f1e3;
      --paper-deep: #e3d4b7;
      --ink: #17201d;
      --muted: #58645f;
      --amber: #d68a1f;
      --teal: #1f6f68;
      --red: #9f3328;
      --line: rgba(23, 32, 29, 0.18);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(214, 138, 31, 0.2), transparent 34rem),
        linear-gradient(135deg, var(--paper), #fffaf0 54%, var(--paper-deep));
      font-family: "Aptos", "Segoe UI", sans-serif;
    }
    main { width: min(1180px, calc(100vw - 32px)); margin: 0 auto; padding: 48px 0 72px; }
    .hero {
      border: 1px solid var(--line);
      background: rgba(255, 250, 240, 0.72);
      padding: clamp(28px, 5vw, 56px);
      box-shadow: 14px 14px 0 rgba(23, 32, 29, 0.08);
    }
    .eyebrow {
      color: var(--teal);
      font-family: "Cascadia Mono", "Consolas", monospace;
      font-size: 0.8rem;
      letter-spacing: 0.18em;
      text-transform: uppercase;
    }
    h1 {
      max-width: 820px;
      margin: 12px 0 16px;
      font-family: "Bahnschrift", "Arial Narrow", sans-serif;
      font-size: clamp(2.5rem, 8vw, 6.8rem);
      line-height: 0.88;
      letter-spacing: -0.06em;
      text-transform: uppercase;
    }
    .summary { max-width: 760px; color: var(--muted); font-size: 1.08rem; line-height: 1.65; }
    .runway {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
      margin-top: 28px;
      font-family: "Cascadia Mono", "Consolas", monospace;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 0.78rem;
    }
    .runway span { border-top: 7px solid var(--teal); padding-top: 8px; }
    .runway span:first-child { border-color: var(--red); }
    .runway span:nth-child(2) { border-color: var(--amber); }
    .risk-block { margin-top: 42px; }
    h2 {
      margin: 0 0 16px;
      font-family: "Cascadia Mono", "Consolas", monospace;
      font-size: 0.92rem;
      letter-spacing: 0.16em;
      text-transform: uppercase;
    }
    .command-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
    .command-card {
      min-height: 100%;
      border: 1px solid var(--line);
      background: rgba(255, 250, 240, 0.84);
      padding: 20px;
    }
    .card-topline { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
    .command-name {
      font-family: "Bahnschrift", "Arial Narrow", sans-serif;
      font-size: 1.7rem;
      letter-spacing: -0.03em;
      text-transform: uppercase;
    }
    .risk-pill {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 5px 10px;
      font-family: "Cascadia Mono", "Consolas", monospace;
      font-size: 0.7rem;
      text-transform: uppercase;
    }
    .risk-high .risk-pill { color: white; background: var(--red); }
    .risk-medium .risk-pill { color: var(--ink); background: var(--amber); }
    .risk-low .risk-pill { color: white; background: var(--teal); }
    .purpose { color: var(--muted); line-height: 1.5; min-height: 3em; }
    dl { display: grid; grid-template-columns: 88px 1fr; gap: 8px 12px; font-size: 0.88rem; }
    dt { color: var(--teal); font-family: "Cascadia Mono", "Consolas", monospace; text-transform: uppercase; font-size: 0.68rem; }
    dd { margin: 0; overflow-wrap: anywhere; }
    .lists { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 16px; }
    h3 { margin: 0 0 8px; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.12em; }
    ul { margin: 0; padding-left: 18px; color: var(--muted); overflow-wrap: anywhere; }
    li + li { margin-top: 4px; }
    @media (max-width: 720px) {
      .runway, .lists { grid-template-columns: 1fr; }
      dl { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <div class="eyebrow">harness command registry</div>
      <h1>Risk runway</h1>
      <p class="summary">A static local flight deck for the Codex/Flywheel harness. Inspect delegated scripts, output schemas, default artifacts, and validation slices before launching anything expensive.</p>
      <div class="runway" aria-label="Risk runway legend"><span>High risk</span><span>Medium risk</span><span>Low risk</span></div>
    </section>
    __CARDS__
  </main>
</body>
</html>
""".replace("__CARDS__", "\n".join(cards))


def build_registry_summary(manifest: dict, *, html_path: str) -> dict:
    commands = manifest.get("commands", []) if isinstance(manifest.get("commands"), list) else []
    risk_counts: dict[str, int] = {}
    schemas = sorted({
        str(schema)
        for row in commands
        if isinstance(row, dict)
        for schema in (row.get("schemas", []) if isinstance(row.get("schemas"), list) else [])
        if schema
    })
    for row in commands:
        if not isinstance(row, dict):
            continue
        risk = str(row.get("long_running_risk", "low"))
        risk_counts[risk] = risk_counts.get(risk, 0) + 1
    return {
        "schema": "harness.command-registry-html/v1",
        "manifest_schema": manifest.get("schema", ""),
        "entrypoint": manifest.get("entrypoint", ""),
        "dispatcher": manifest.get("dispatcher", ""),
        "html_path": html_path,
        "command_count": len(commands),
        "command_names": [str(row.get("name", "")) for row in commands if isinstance(row, dict) and row.get("name")],
        "risk_counts": risk_counts,
        "schema_count": len(schemas),
        "schemas": schemas,
    }


def _store_manifest(manifest: dict, *, store_root: str, run_id: str, artifacts: list[tuple[str, str]]) -> list[dict]:
    if not store_root:
        return []
    store = FileBackedHarnessStore(Path(store_root))
    outputs = [
        store.put_receipt(
            kind="harness_executable_manifest",
            body=manifest,
            run_id=run_id,
            verdict="MANIFEST_RECORDED",
        )
    ]
    for path_text, label in artifacts:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--print-command", action="store_true", help="print the target command without executing it")
    subparsers = parser.add_subparsers(dest="command_name", required=True)

    manifest = subparsers.add_parser("manifest", help="emit executable surface manifest")
    _add_common_io(manifest)

    registry = subparsers.add_parser("registry", help="emit static local HTML command registry")
    registry.add_argument("--store-root", default=DEFAULT_STORE_ROOT)
    registry.add_argument("--out", default="C:/tmp/harness_command_registry.html")
    registry.add_argument("--summary-out", default="C:/tmp/harness_command_registry.json")
    registry.add_argument("--run-id", default="")

    benchmarks = subparsers.add_parser("benchmarks", help="emit weighted benchmark profile manifest")
    _add_common_io(benchmarks)
    benchmarks.add_argument("--providers", default="serve,codex,ollama,claude,opencode,dry")
    benchmarks.add_argument("--artifact-roots", default="C:/tmp;C:/dev/local-model/artifacts")
    benchmarks.add_argument("--max-artifacts", type=int, default=200)

    forum_route = subparsers.add_parser("forum-route", help="emit metadata-only Forum route receipts")
    _add_common_io(forum_route)
    forum_route.add_argument("--route", action="append", default=[])
    forum_route.add_argument("--observed-decided", default="")
    forum_route.add_argument("--observed-confidence", default="")
    forum_route.add_argument("--observed-needs-escalation", default="")
    forum_route.add_argument("--observed-domain", default="")
    forum_route.add_argument("--observed-intent", default="")
    forum_route.add_argument("--observed-posture", default="")
    forum_route.add_argument("--observed-proof-lane", default="")
    forum_route.add_argument("--observed-domain-lane", default="")
    forum_route.add_argument("--observed-human-contract", default="")
    forum_route.add_argument("--observed-source", default="forum.route")

    mcp_health = subparsers.add_parser("mcp-health", help="emit metadata-only MCP/tool health receipts")
    _add_common_io(mcp_health)
    mcp_health.add_argument("--tools", default="index,forum,telos,gather,crucible,aleph,mneme,relay,plexus,pubscan,local-model")
    mcp_health.add_argument("--observation", action="append", default=[])

    coverage = subparsers.add_parser("benchmark-coverage", help="compare benchmark profile against scorecards")
    _add_common_io(coverage)
    coverage.add_argument("--profile", required=True)
    coverage.add_argument("--artifacts", default="")

    comparison = subparsers.add_parser("comparison", help="synthesize Codex-vs-Flywheel comparison report")
    _add_common_io(comparison)
    comparison.add_argument("--artifacts", default="")
    comparison.add_argument("--flywheel-role", default="flywheel")
    comparison.add_argument("--codex-role", default="codex")

    execution_matrix = subparsers.add_parser("execution-matrix", help="emit benchmark execution matrix without running benchmarks")
    _add_common_io(execution_matrix)
    execution_matrix.add_argument("--providers", default="serve,codex,ollama,claude,opencode,dry")
    execution_matrix.add_argument("--artifact-dir", default="C:/tmp/harness_benchmark_matrix_20260709")

    schematic = subparsers.add_parser("schematic-drift", help="check closed-loop schematic drift without running benchmarks")
    _add_common_io(schematic)
    schematic.add_argument("--graph", default="C:/dev/local-model/project-docs/schematics/closed-loop-integration.graph.json")
    schematic.add_argument("--report", default="C:/dev/local-model/project-docs/records/CLOSED-LOOP-INTEGRATION-SCHEMATIC-2026-07-09.md")

    agentic = subparsers.add_parser("agentic-tasks", help="emit non-executing agentic task manifest")
    _add_common_io(agentic)
    agentic.add_argument("--task-set", default="C:/dev/local-model/benchmarks/agentic-task-set-v1.json")
    agentic.add_argument("--adapter", default="C:/dev/local-model/benchmarks/agentic-task-set-adapter-v1.json")
    agentic.add_argument("--artifact-dir", default="C:/tmp/agentic_task_runs")
    agentic.add_argument("--provider-roles", default="dry")

    cross = subparsers.add_parser("cross-harness", help="emit non-executing cross-harness manifest")
    _add_common_io(cross)
    cross.add_argument("--task-set", default="C:/dev/local-model/benchmarks/agentic-task-set-v1.json")
    cross.add_argument("--contract", default="C:/dev/local-model/benchmarks/cross-harness-adapter-contract-v1.json")
    cross.add_argument("--provider-roles", default="")
    cross.add_argument("--artifact-dir", default="C:/tmp/cross_harness_runs")

    adapter_runtime = subparsers.add_parser("adapter-runtime", help="emit metadata-only adapter/runtime compatibility matrix")
    _add_common_io(adapter_runtime)
    adapter_runtime.add_argument("--contract", default="C:/dev/local-model/benchmarks/cross-harness-adapter-contract-v1.json")
    adapter_runtime.add_argument("--endpoint-profiles", default="")
    adapter_runtime.add_argument("--endpoint-auth-status", default="")

    embodied = subparsers.add_parser("embodied-realtime", help="emit non-executing embodied realtime multimodal benchmark plan")
    _add_common_io(embodied)
    embodied.add_argument("--contract", default="C:/dev/local-model/benchmarks/embodied-realtime-multimodal-v1.json")
    embodied.add_argument("--providers", default="dry")
    embodied.add_argument("--latency-budgets-ms", default="250,500,1000")
    embodied.add_argument("--artifact-dir", default="C:/tmp/embodied_realtime_multimodal")

    claims = subparsers.add_parser("model-card-claims", help="emit non-executing model-card claim table")
    _add_common_io(claims)
    claims.add_argument("--contract", default="C:/dev/local-model/benchmarks/embodied-realtime-multimodal-v1.json")
    claims.add_argument("--evidence", default="")
    claims.add_argument("--artifact-dir", default="C:/tmp/model_card_claims")

    hardening = subparsers.add_parser("tool-hardening", help="generate enterprise hardening plan from tool readiness")
    _add_common_io(hardening)
    hardening.add_argument("--readiness-artifact", required=True)

    classifier = subparsers.add_parser("classifier-friction", help="run guardrail/accountability friction benchmark")
    _add_common_io(classifier)
    classifier.add_argument("--providers", default="dry,serve,codex")
    classifier.add_argument("--modes-to-test", default="guardrail_on,guardrail_off,accountability_first")
    classifier.add_argument("--allow-online", action="store_true")
    classifier.add_argument("--endpoint-model", default="gpt-5.3-codex-spark")
    classifier.add_argument("--modes", default="plan")
    classifier.add_argument("--serve-url", default="http://127.0.0.1:8765")
    classifier.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    classifier.add_argument("--local-model", default="qwen2.5:7b")
    classifier.add_argument("--task-id", default="")
    classifier.add_argument("--max-tasks", type=int, default=1)
    classifier.add_argument("--timeout-seconds", type=int, default=120)
    classifier.add_argument("--max-tokens", type=int, default=500)

    endpoint_gate = subparsers.add_parser("endpoint-gate", help="run bounded local model endpoint health/generation gate")
    _add_common_io(endpoint_gate)
    endpoint_gate.add_argument("--profile-artifact", default="C:/tmp/model_endpoint_profiles_20260709.json")
    endpoint_gate.add_argument("--models", default="")
    endpoint_gate.add_argument("--backends", default="")
    endpoint_gate.add_argument("--timeout-seconds", type=float, default=30.0)
    endpoint_gate.add_argument("--max-tokens", type=int, default=64)
    endpoint_gate.add_argument("--strict-exit", action="store_true")

    launch_readiness = subparsers.add_parser("endpoint-launch-readiness", help="emit local model serve launch readiness and port-owner diagnostics")
    _add_common_io(launch_readiness)
    launch_readiness.add_argument("--profile-artifact", default="C:/tmp/model_endpoint_profiles_20260709.json")
    launch_readiness.add_argument("--models", default="")
    launch_readiness.add_argument("--backends", default="serve")
    launch_readiness.add_argument("--strict-exit", action="store_true")

    serve_launch = subparsers.add_parser("serve-launch", help="plan or start local harness/serve.py from endpoint profiles")
    _add_common_io(serve_launch)
    serve_launch.add_argument("--profile-artifact", default="C:/tmp/model_endpoint_profiles_20260709.json")
    serve_launch.add_argument("--models", default="")
    serve_launch.add_argument("--serve-python", default=_default_serve_python())
    serve_launch.add_argument("--start", action="store_true")
    serve_launch.add_argument("--wait-seconds", type=float, default=0.0)
    serve_launch.add_argument("--log-dir", default="C:/tmp/local_model_serve_logs")
    serve_launch.add_argument("--terminate-on-timeout", action="store_true")
    serve_launch.add_argument("--strict-exit", action="store_true")

    serve_resource = subparsers.add_parser("serve-resource", help="emit GPU resource preflight before local serve launch")
    _add_common_io(serve_resource)
    serve_resource.add_argument("--profile-artifact", default="C:/tmp/model_endpoint_profiles_20260709.json")
    serve_resource.add_argument("--models", default="")
    serve_resource.add_argument("--strict-exit", action="store_true")

    model_publish = subparsers.add_parser("model-publish", help="generate 14B/32B model naming and publish plan")
    _add_common_io(model_publish)
    model_publish.add_argument("--release-readiness-artifact", required=True)
    model_publish.add_argument("--name-prefix", default="Flywheel-Local-Coder")

    plan = subparsers.add_parser("plan", help="emit closed-loop seed dry plan")
    plan.add_argument("--out", default="C:/tmp/harness_closed_loop_seed_plan.json")

    seed = subparsers.add_parser("seed", help="execute the closed-loop seed run")
    seed.add_argument("--store-root", default=DEFAULT_STORE_ROOT)
    seed.add_argument("--artifact-dir", default=DEFAULT_SEED_DIR)
    seed.add_argument("--out", default="C:/tmp/harness_closed_loop_seed.json")
    seed.add_argument("--unisonai-repair-json", action="store_true")
    seed.add_argument("--strict-exit", action="store_true")

    outcome = subparsers.add_parser("outcome", help="synthesize closed-loop outcome")
    _add_common_io(outcome)
    outcome.add_argument("--input", default="")

    query = subparsers.add_parser("query", help="query the file-backed harness store")
    _add_common_io(query)
    query.add_argument("--limit", type=int, default=50)

    readiness = subparsers.add_parser("readiness", help="run one metadata-only readiness receipt")
    readiness.add_argument(
        "target",
        choices=["context", "tools", "model-endpoints", "model-release", "gather", "endpoint-auth", "pubscan"],
    )
    _add_common_io(readiness)
    readiness.add_argument("--roots", default="")
    readiness.add_argument("--tools", default="")
    readiness.add_argument("--tool-root", action="append", default=[])
    readiness.add_argument("--models", default="")
    readiness.add_argument("--serve-url", default="")
    readiness.add_argument("--serve-url-14b", default="")
    readiness.add_argument("--serve-url-32b", default="")
    readiness.add_argument("--serve-runtime-14b", default="")
    readiness.add_argument("--serve-runtime-32b", default="")
    readiness.add_argument("--ollama-url", default="")
    readiness.add_argument("--base-root", default="")
    readiness.add_argument("--artifact-roots", default="")
    readiness.add_argument("--gather-root", default="")
    readiness.add_argument("--config-roots", default="")

    return parser


def _append_if(command: list[str], flag: str, value: str) -> None:
    if value:
        command.extend([flag, value])


def _common_outputs(command: list[str], args) -> None:
    _append_if(command, "--out", args.out)
    _append_if(command, "--markdown-out", args.markdown_out)
    _append_if(command, "--store-root", args.store_root)
    _append_if(command, "--run-id", args.run_id)


def _readiness_command(args) -> list[str]:
    py = args.python
    if args.target == "context":
        command = [py, "scripts/run_context_inventory.py"]
        _append_if(command, "--roots", args.roots)
        _common_outputs(command, args)
        return command
    if args.target == "tools":
        command = [py, "scripts/run_tool_readiness_receipts.py"]
        _append_if(command, "--tools", args.tools)
        _append_if(command, "--base-root", args.base_root)
        for tool_root in args.tool_root:
            command.extend(["--tool-root", tool_root])
        _common_outputs(command, args)
        return command
    if args.target == "model-endpoints":
        command = [py, "scripts/run_model_endpoint_profiles.py"]
        _append_if(command, "--models", args.models)
        _append_if(command, "--base-root", args.base_root)
        _append_if(command, "--serve-url", args.serve_url)
        _append_if(command, "--serve-url-14b", args.serve_url_14b)
        _append_if(command, "--serve-url-32b", args.serve_url_32b)
        _append_if(command, "--serve-runtime-14b", args.serve_runtime_14b)
        _append_if(command, "--serve-runtime-32b", args.serve_runtime_32b)
        _append_if(command, "--ollama-url", args.ollama_url)
        _common_outputs(command, args)
        return command
    if args.target == "model-release":
        command = [py, "scripts/run_model_release_readiness.py"]
        _append_if(command, "--base-root", args.base_root)
        _append_if(command, "--artifact-roots", args.artifact_roots)
        _common_outputs(command, args)
        return command
    if args.target == "gather":
        command = [py, "scripts/run_gather_readiness.py"]
        _append_if(command, "--gather-root", args.gather_root)
        _append_if(command, "--config-roots", args.config_roots)
        _common_outputs(command, args)
        return command
    if args.target == "endpoint-auth":
        command = [py, "scripts/run_endpoint_auth_status.py"]
        _common_outputs(command, args)
        return command
    if args.target == "pubscan":
        command = [py, "scripts/run_pubscan_resource_profiles.py"]
        _common_outputs(command, args)
        return command
    raise ValueError(f"unknown readiness target: {args.target}")


def build_command(args, *, repo_root: Path) -> list[str]:
    py = args.python
    if args.command_name == "benchmarks":
        command = [
            py,
            "scripts/run_benchmark_profile_manifest.py",
            "--providers",
            args.providers,
            "--artifact-roots",
            args.artifact_roots,
            "--max-artifacts",
            str(args.max_artifacts),
        ]
        _common_outputs(command, args)
        return command
    if args.command_name == "forum-route":
        command = [py, "scripts/run_forum_route_receipts.py"]
        for route_text in args.route:
            command.extend(["--route", route_text])
        _append_if(command, "--observed-decided", args.observed_decided)
        _append_if(command, "--observed-confidence", args.observed_confidence)
        _append_if(command, "--observed-needs-escalation", args.observed_needs_escalation)
        _append_if(command, "--observed-domain", args.observed_domain)
        _append_if(command, "--observed-intent", args.observed_intent)
        _append_if(command, "--observed-posture", args.observed_posture)
        _append_if(command, "--observed-proof-lane", args.observed_proof_lane)
        _append_if(command, "--observed-domain-lane", args.observed_domain_lane)
        _append_if(command, "--observed-human-contract", args.observed_human_contract)
        _append_if(command, "--observed-source", args.observed_source)
        _common_outputs(command, args)
        return command
    if args.command_name == "mcp-health":
        command = [
            py,
            "scripts/run_mcp_tool_health_receipts.py",
            "--tools",
            args.tools,
        ]
        for observation in args.observation:
            command.extend(["--observation", observation])
        _common_outputs(command, args)
        return command
    if args.command_name == "benchmark-coverage":
        command = [
            py,
            "scripts/run_benchmark_profile_coverage.py",
            "--profile",
            args.profile,
        ]
        _append_if(command, "--artifacts", args.artifacts)
        _common_outputs(command, args)
        return command
    if args.command_name == "comparison":
        command = [
            py,
            "scripts/run_harness_comparison_report.py",
            "--artifacts",
            args.artifacts,
            "--flywheel-role",
            args.flywheel_role,
            "--codex-role",
            args.codex_role,
        ]
        _common_outputs(command, args)
        return command
    if args.command_name == "execution-matrix":
        command = [
            py,
            "scripts/run_benchmark_execution_matrix.py",
            "--providers",
            args.providers,
            "--artifact-dir",
            args.artifact_dir,
        ]
        _common_outputs(command, args)
        return command
    if args.command_name == "schematic-drift":
        command = [
            py,
            "scripts/run_schematic_drift_check.py",
            "--graph",
            args.graph,
            "--report",
            args.report,
        ]
        _common_outputs(command, args)
        return command
    if args.command_name == "agentic-tasks":
        command = [
            py,
            "scripts/run_agentic_task_set_manifest.py",
            "--task-set",
            args.task_set,
            "--adapter",
            args.adapter,
            "--artifact-dir",
            args.artifact_dir,
            "--provider-roles",
            args.provider_roles,
        ]
        _common_outputs(command, args)
        return command
    if args.command_name == "cross-harness":
        command = [
            py,
            "scripts/run_cross_harness_manifest.py",
            "--task-set",
            args.task_set,
            "--contract",
            args.contract,
            "--artifact-dir",
            args.artifact_dir,
        ]
        _append_if(command, "--provider-roles", args.provider_roles)
        _common_outputs(command, args)
        return command
    if args.command_name == "adapter-runtime":
        command = [
            py,
            "scripts/run_adapter_runtime_matrix.py",
            "--contract",
            args.contract,
        ]
        _append_if(command, "--endpoint-profiles", args.endpoint_profiles)
        _append_if(command, "--endpoint-auth-status", args.endpoint_auth_status)
        _common_outputs(command, args)
        return command
    if args.command_name == "embodied-realtime":
        command = [
            py,
            "scripts/run_embodied_realtime_multimodal_plan.py",
            "--contract",
            args.contract,
            "--providers",
            args.providers,
            "--latency-budgets-ms",
            args.latency_budgets_ms,
            "--artifact-dir",
            args.artifact_dir,
        ]
        _common_outputs(command, args)
        return command
    if args.command_name == "model-card-claims":
        command = [
            py,
            "scripts/run_model_card_claim_table.py",
            "--contract",
            args.contract,
            "--artifact-dir",
            args.artifact_dir,
        ]
        _append_if(command, "--evidence", args.evidence)
        _common_outputs(command, args)
        return command
    if args.command_name == "tool-hardening":
        command = [
            py,
            "scripts/run_tool_hardening_plan.py",
            "--readiness-artifact",
            args.readiness_artifact,
        ]
        _common_outputs(command, args)
        return command
    if args.command_name == "classifier-friction":
        command = [
            py,
            "scripts/run_classifier_friction_benchmark.py",
            "--providers",
            args.providers,
            "--modes-to-test",
            args.modes_to_test,
            "--endpoint-model",
            args.endpoint_model,
            "--modes",
            args.modes,
            "--serve-url",
            args.serve_url,
            "--ollama-url",
            args.ollama_url,
            "--local-model",
            args.local_model,
            "--max-tasks",
            str(args.max_tasks),
            "--timeout-seconds",
            str(args.timeout_seconds),
            "--max-tokens",
            str(args.max_tokens),
        ]
        _append_if(command, "--task-id", args.task_id)
        if args.allow_online:
            command.append("--allow-online")
        _common_outputs(command, args)
        return command
    if args.command_name == "endpoint-gate":
        command = [
            py,
            "scripts/run_model_endpoint_gate.py",
            "--profile-artifact",
            args.profile_artifact,
            "--timeout-seconds",
            str(args.timeout_seconds),
            "--max-tokens",
            str(args.max_tokens),
        ]
        _append_if(command, "--models", args.models)
        _append_if(command, "--backends", args.backends)
        if args.strict_exit:
            command.append("--strict-exit")
        _common_outputs(command, args)
        return command
    if args.command_name == "endpoint-launch-readiness":
        command = [
            py,
            "scripts/run_local_model_launch_readiness.py",
            "--profile-artifact",
            args.profile_artifact,
        ]
        _append_if(command, "--models", args.models)
        _append_if(command, "--backends", args.backends)
        if args.strict_exit:
            command.append("--strict-exit")
        _common_outputs(command, args)
        return command
    if args.command_name == "serve-launch":
        command = [
            py,
            "scripts/run_local_model_serve_launcher.py",
            "--profile-artifact",
            args.profile_artifact,
            "--serve-python",
            args.serve_python,
            "--wait-seconds",
            str(args.wait_seconds),
            "--log-dir",
            args.log_dir,
        ]
        _append_if(command, "--models", args.models)
        if args.start:
            command.append("--start")
        if args.terminate_on_timeout:
            command.append("--terminate-on-timeout")
        if args.strict_exit:
            command.append("--strict-exit")
        _common_outputs(command, args)
        return command
    if args.command_name == "serve-resource":
        command = [
            py,
            "scripts/run_local_model_resource_preflight.py",
            "--profile-artifact",
            args.profile_artifact,
        ]
        _append_if(command, "--models", args.models)
        if args.strict_exit:
            command.append("--strict-exit")
        _common_outputs(command, args)
        return command
    if args.command_name == "model-publish":
        command = [
            py,
            "scripts/run_model_publish_plan.py",
            "--release-readiness-artifact",
            args.release_readiness_artifact,
            "--name-prefix",
            args.name_prefix,
        ]
        _common_outputs(command, args)
        return command
    if args.command_name == "plan":
        return [
            py,
            "scripts/run_closed_loop_benchmark_seed.py",
            "--dry-plan",
            "--out",
            args.out,
        ]
    if args.command_name == "seed":
        command = [
            py,
            "scripts/run_closed_loop_benchmark_seed.py",
            "--store-root",
            args.store_root,
            "--artifact-dir",
            args.artifact_dir,
            "--out",
            args.out,
        ]
        if args.unisonai_repair_json:
            command.append("--unisonai-repair-json")
        if args.strict_exit:
            command.append("--strict-exit")
        return command
    if args.command_name == "outcome":
        command = [py, "scripts/run_closed_loop_outcome_report.py"]
        _append_if(command, "--input", args.input)
        _common_outputs(command, args)
        return command
    if args.command_name == "query":
        command = [
            py,
            "scripts/run_harness_store_query.py",
            "--store-root",
            args.store_root,
            "--limit",
            str(args.limit),
        ]
        _append_if(command, "--run-id", args.run_id)
        _append_if(command, "--out", args.out)
        _append_if(command, "--markdown-out", args.markdown_out)
        return command
    if args.command_name == "readiness":
        return _readiness_command(args)
    raise ValueError(f"unknown command: {args.command_name}")


def format_command(command: list[str]) -> str:
    parts = []
    for part in command:
        if any(ch.isspace() for ch in part):
            parts.append('"' + part.replace('"', '\\"') + '"')
        else:
            parts.append(part)
    return " ".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = _repo_root()
    if args.command_name == "manifest":
        manifest = build_manifest(store_root=args.store_root)
        json_text = json.dumps(manifest, indent=2, sort_keys=True)
        md_text = render_manifest_markdown(manifest)
        json_path = _write(args.out, json_text)
        md_path = _write(args.markdown_out, md_text)
        store_outputs = _store_manifest(
            manifest,
            store_root=args.store_root,
            run_id=args.run_id,
            artifacts=[
                (json_path, "harness-executable-manifest-json"),
                (md_path, "harness-executable-manifest-markdown"),
            ],
        )
        if store_outputs:
            manifest = {**manifest, "store_outputs": store_outputs}
            json_text = json.dumps(manifest, indent=2, sort_keys=True)
        print(json_text)
        return 0
    if args.command_name == "registry":
        manifest = build_manifest(store_root=args.store_root)
        html_text = render_registry_html(manifest)
        html_path = _write(args.out, html_text)
        summary = build_registry_summary(manifest, html_path=html_path)
        summary_path = _write(args.summary_out, json.dumps(summary, indent=2, sort_keys=True))
        store_outputs = []
        if args.store_root:
            store = FileBackedHarnessStore(Path(args.store_root))
            store_outputs = [
                store.put_receipt(
                    kind="harness_command_registry",
                    body=summary,
                    run_id=args.run_id,
                    verdict="REGISTRY_RECORDED",
                )
            ]
            if html_path:
                store_outputs.append(store.copy_artifact(Path(html_path), run_id=args.run_id, label="harness-command-registry-html"))
            if summary_path:
                store_outputs.append(store.copy_artifact(Path(summary_path), run_id=args.run_id, label="harness-command-registry-json"))
        if store_outputs:
            summary = {**summary, "store_outputs": store_outputs}
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    command = build_command(args, repo_root=root)
    if args.print_command:
        print(format_command(command))
        return 0
    completed = subprocess.run(command, cwd=str(root), check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
