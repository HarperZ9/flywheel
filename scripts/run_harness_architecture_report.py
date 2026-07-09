"""Emit a metadata-only harness architecture and endpoint report."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore

SCHEMA = "harness.architecture-report/v1"
DEFAULT_DIST = Path("C:/dev/local-model/artifacts/exe")


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact(path: Path, schema: str = "") -> dict[str, Any]:
    payload = _load(path)
    return {
        "path": str(path),
        "exists": path.exists(),
        "expected_schema": schema,
        "observed_schema": payload.get("schema") if payload else None,
        "schema_matches": bool(payload) and (not schema or payload.get("schema") == schema),
    }


def _command_names(manifest: dict[str, Any]) -> list[str]:
    return [str(row.get("name")) for row in manifest.get("commands", []) if isinstance(row, dict)]


def _endpoint_summary(endpoint_profiles: dict[str, Any]) -> dict[str, Any]:
    profiles = endpoint_profiles.get("profiles") or []
    models = sorted({str(row.get("model")) for row in profiles if isinstance(row, dict) and row.get("model")})
    backends = sorted({str(row.get("backend")) for row in profiles if isinstance(row, dict) and row.get("backend")})
    return {
        "schema": "harness.architecture-report.endpoints/v1",
        "profile_count": len(profiles),
        "models": models,
        "backends": backends,
        "serve_profiles": [row for row in profiles if isinstance(row, dict) and row.get("backend") == "serve"],
        "ollama_profiles": [row for row in profiles if isinstance(row, dict) and row.get("backend") == "ollama"],
        "agentic_profiles": sum(1 for row in profiles if isinstance(row, dict) and row.get("supports_agentic_workflow")),
    }


def _tool_summary(tool_contract: dict[str, Any]) -> dict[str, Any]:
    tools = tool_contract.get("tools") or []
    return {
        "schema": "harness.architecture-report.tools/v1",
        "tool_count": len(tools),
        "tools": [str(row.get("tool")) for row in tools if isinstance(row, dict)],
        "enterprise_ready_static": (tool_contract.get("summary") or {}).get("enterprise_ready_static"),
        "roots_missing": (tool_contract.get("summary") or {}).get("roots_missing"),
        "readiness_verdicts": {
            str(row.get("tool")): ((row.get("readiness") or {}).get("verdict"))
            for row in tools
            if isinstance(row, dict)
        },
    }


def _model_release_summary(readiness: dict[str, Any], publish: dict[str, Any]) -> dict[str, Any]:
    release_summary = readiness.get("summary") or {}
    publish_summary = publish.get("summary") or {}
    candidates = publish.get("models") or publish.get("model_plans") or []
    candidate_names = []
    if isinstance(candidates, list):
        for row in candidates:
            if isinstance(row, dict):
                name = row.get("candidate_name") or row.get("name") or row.get("slug")
                if name:
                    candidate_names.append(str(name))
    return {
        "schema": "harness.architecture-report.model-release/v1",
        "release_readiness_present": bool(readiness),
        "publish_plan_present": bool(publish),
        "release_summary": release_summary,
        "publish_summary": publish_summary,
        "candidate_names": candidate_names,
        "publish_status": publish_summary.get("status") or publish_summary.get("verdict"),
        "release_ready_models": release_summary.get("release_ready_models"),
        "models_with_weights": release_summary.get("models_with_weights"),
    }


def _context_summary(context_inventory: dict[str, Any]) -> dict[str, Any]:
    summary = context_inventory.get("summary") or {}
    roots = context_inventory.get("roots") or []
    return {
        "schema": "harness.architecture-report.context-inventory/v1",
        "present": bool(context_inventory),
        "roots_requested": len(context_inventory.get("roots_requested") or []),
        "existing_roots": summary.get("existing_roots", 0),
        "root_count": summary.get("roots", len(roots)),
        "entries": summary.get("entries", 0),
        "sensitive_name_entries": summary.get("sensitive_name_entries", 0),
        "label_counts": summary.get("label_counts", {}),
        "truncated_roots": sum(1 for row in roots if isinstance(row, dict) and row.get("truncated")),
    }


def _pubscan_summary(pubscan_profiles: dict[str, Any]) -> dict[str, Any]:
    pubscan = pubscan_profiles.get("pubscan") or {}
    pubscan_summary = pubscan.get("summary") or {}
    native = pubscan_profiles.get("native_rendering") or {}
    native_summary = native.get("summary") or {}
    compute = pubscan_profiles.get("compute") or {}
    storage = pubscan_profiles.get("storage") or {}
    storage_summary = storage.get("summary") or {}
    return {
        "schema": "harness.architecture-report.pubscan/v1",
        "present": bool(pubscan_profiles),
        "root": pubscan.get("root", ""),
        "root_exists": pubscan.get("exists", False),
        "repo_count": pubscan.get("count", 0),
        "profiled_entrypoints": pubscan_summary.get("profiled_entrypoints", 0),
        "source_only": pubscan_summary.get("source_only", 0),
        "unverified": pubscan_summary.get("unverified", 0),
        "native_rendering_candidates": pubscan_summary.get("native_rendering_candidates", 0),
        "native_candidate_matches": native_summary.get("candidate_matches", 0),
        "local_cpu_cores": (compute.get("local_cpu") or {}).get("logical_cores", 0),
        "local_gpu_status": (compute.get("local_gpu") or {}).get("status", "unknown"),
        "storage_available_roots": storage_summary.get("available_roots", 0),
        "zero_dependency_policy": pubscan_profiles.get("zero_dependency_policy", {}),
    }


def build_report(
    *,
    release_manifest_path: Path,
    executable_manifest_path: Path,
    context_inventory_path: Path,
    pubscan_profiles_path: Path,
    endpoint_profiles_path: Path,
    model_release_path: Path,
    model_publish_path: Path,
    tool_contract_path: Path,
    runtime_contract_path: Path,
    codex_mcp_contract_path: Path,
    enterprise_readiness_path: Path,
    package_doctor_path: Path,
) -> dict[str, Any]:
    release_manifest = _load(release_manifest_path)
    executable_manifest = _load(executable_manifest_path)
    context_inventory = _load(context_inventory_path)
    pubscan_profiles = _load(pubscan_profiles_path)
    endpoint_profiles = _load(endpoint_profiles_path)
    model_release = _load(model_release_path)
    model_publish = _load(model_publish_path)
    tool_contract = _load(tool_contract_path)
    runtime_contract = _load(runtime_contract_path)
    codex_mcp = _load(codex_mcp_contract_path)
    enterprise_readiness = _load(enterprise_readiness_path)
    package_doctor = _load(package_doctor_path)
    artifacts = {
        "release_manifest": _artifact(release_manifest_path, "harness.local-executable-release/v1"),
        "executable_manifest": _artifact(executable_manifest_path, "harness.executable-manifest/v1"),
        "context_inventory": _artifact(context_inventory_path, "harness.context-inventory/v1"),
        "pubscan_profiles": _artifact(pubscan_profiles_path, "harness.pubscan-resource-profiles/v1"),
        "endpoint_profiles": _artifact(endpoint_profiles_path, "harness.model-endpoint-profiles/v1"),
        "model_release_readiness": _artifact(model_release_path, "harness.model-release-readiness/v1"),
        "model_publish_plan": _artifact(model_publish_path, "harness.model-publish-plan/v1"),
        "tool_contract": _artifact(tool_contract_path, "harness.tool-integration-contract/v1"),
        "runtime_contract": _artifact(runtime_contract_path, "harness.runtime-activation-contract/v1"),
        "codex_mcp_contract": _artifact(codex_mcp_contract_path, "harness.codex-mcp-launch-contract/v1"),
        "enterprise_readiness": _artifact(enterprise_readiness_path, "harness.enterprise-readiness-report/v1"),
        "package_doctor": _artifact(package_doctor_path, "harness.package-ship-doctor/v1"),
    }
    verified_facts = []
    assumptions = []
    if endpoint_profiles:
        verified_facts.append("14B/32B endpoint profiles are represented by the endpoint profile artifact.")
    else:
        assumptions.append("Endpoint profiles were not present when this report was generated.")
    if model_release:
        verified_facts.append("14B/32B model release readiness is represented by the model release readiness artifact.")
    else:
        assumptions.append("Model release readiness was not present when this report was generated.")
    if model_publish:
        verified_facts.append("14B/32B naming and publication plan is represented by the model publish plan artifact.")
    else:
        assumptions.append("Model publish plan was not present when this report was generated.")
    if context_inventory:
        verified_facts.append("Scratch, temp, session, and benchmark context surfaces are represented by the metadata-only context inventory.")
    else:
        assumptions.append("Context inventory was not present when this report was generated.")
    if pubscan_profiles:
        verified_facts.append("Pubscan repositories, native rendering candidates, local compute, and storage surfaces are represented by the pubscan resource profile artifact.")
    else:
        assumptions.append("Pubscan resource profiles were not present when this report was generated.")
    if tool_contract:
        verified_facts.append("Tool roots and sidecar readiness are represented by the tool integration contract.")
    else:
        assumptions.append("Tool integration contract was absent when this report was generated.")
    if codex_mcp:
        verified_facts.append("Codex MCP launch and fallback profiles are represented by the Codex MCP contract.")
    else:
        assumptions.append("Codex MCP launch contract was absent when this report was generated.")
    if package_doctor:
        verified_facts.append("The package doctor sidecar is present and contributes release-gate status.")
    else:
        assumptions.append("Package doctor sidecar is generated after package assembly and may be absent in pre-package reports.")
    return {
        "schema": SCHEMA,
        "created_utc": _now(),
        "dependency_posture": "metadata-only architecture report; reads generated manifests/contracts and does not run benchmarks, providers, endpoint probes, token stores, source bodies, or model weights",
        "secret_policy": "reports paths, schemas, counts, booleans, command names, and non-secret endpoint URLs only; env values and credentials are not recorded",
        "artifacts": artifacts,
        "executable_surface": {
            "schema": "harness.architecture-report.executable-surface/v1",
            "release_executables": release_manifest.get("executables", []),
            "skipped": release_manifest.get("skipped", []),
            "command_count": len(_command_names(executable_manifest)),
            "commands": _command_names(executable_manifest),
        },
        "context_inventory": _context_summary(context_inventory),
        "pubscan_profiles": _pubscan_summary(pubscan_profiles),
        "local_models": _endpoint_summary(endpoint_profiles),
        "model_release": _model_release_summary(model_release, model_publish),
        "tool_fabric": _tool_summary(tool_contract),
        "runtime_activation": {
            "schema": "harness.architecture-report.runtime/v1",
            "summary": runtime_contract.get("summary", {}),
            "activation_steps": runtime_contract.get("activation_steps", []),
        },
        "codex_mcp": {
            "schema": "harness.architecture-report.codex-mcp/v1",
            "summary": codex_mcp.get("summary", {}),
            "servers": codex_mcp.get("servers", []),
            "session_reload_boundary": codex_mcp.get("session_reload_boundary", {}),
        },
        "release_gate": {
            "schema": "harness.architecture-report.release-gate/v1",
            "package_doctor_present": bool(package_doctor),
            "package_doctor_verdict": (package_doctor.get("summary") or {}).get("verdict") if package_doctor else None,
            "package_doctor_hard_failures": (package_doctor.get("summary") or {}).get("hard_failures") if package_doctor else None,
        },
        "enterprise_readiness": {
            "schema": "harness.architecture-report.enterprise-readiness/v1",
            "summary": enterprise_readiness.get("summary", {}),
            "tools": [row.get("tool") for row in enterprise_readiness.get("tools", []) if isinstance(row, dict)],
            "report_present": bool(enterprise_readiness),
        },
        "verified_facts": verified_facts,
        "assumptions": assumptions,
        "next_gates": [
            "Keep package-doctor at SHIP_READY before benchmark execution.",
            "Run endpoint-launch-readiness before starting 14B/32B serve profiles.",
            "Run benchmark suites only after architecture/package/runtime surfaces remain reproducible.",
        ],
        "summary": {
            "artifact_count": len(artifacts),
            "artifacts_present": sum(1 for row in artifacts.values() if row["exists"]),
            "schema_mismatches": [name for name, row in artifacts.items() if row["exists"] and not row["schema_matches"]],
            "models": _endpoint_summary(endpoint_profiles)["models"],
            "model_candidate_names": _model_release_summary(model_release, model_publish)["candidate_names"],
            "context_entries": _context_summary(context_inventory)["entries"],
            "pubscan_repositories": _pubscan_summary(pubscan_profiles)["repo_count"],
            "pubscan_profiled_entrypoints": _pubscan_summary(pubscan_profiles)["profiled_entrypoints"],
            "tools": _tool_summary(tool_contract)["tools"],
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Harness architecture and endpoint report",
        "",
        f"Schema: `{report['schema']}`",
        "",
        "## Summary",
        "",
        f"- Artifacts present: {report['summary']['artifacts_present']} / {report['summary']['artifact_count']}",
        f"- Models: {', '.join(report['summary']['models']) or 'none'}",
        f"- Model candidate names: {', '.join(report['summary']['model_candidate_names']) or 'none'}",
        f"- Context entries: {report['summary']['context_entries']}",
        f"- Pubscan repositories: {report['summary']['pubscan_repositories']}",
        f"- Pubscan profiled entrypoints: {report['summary']['pubscan_profiled_entrypoints']}",
        f"- Tools: {', '.join(report['summary']['tools']) or 'none'}",
        f"- Package doctor: {report['release_gate']['package_doctor_verdict'] or 'not present in this report'}",
        "",
        "## Executable surface",
        "",
        f"- Commands: {report['executable_surface']['command_count']}",
        f"- Skipped executables: {', '.join(report['executable_surface']['skipped']) or 'none'}",
        "",
        "## Context inventory",
        "",
        f"- Existing roots: {report['context_inventory']['existing_roots']} / {report['context_inventory']['root_count']}",
        f"- Entries: {report['context_inventory']['entries']}",
        f"- Sensitive-name entries: {report['context_inventory']['sensitive_name_entries']}",
        f"- Truncated roots: {report['context_inventory']['truncated_roots']}",
        "",
        "## Pubscan resources",
        "",
        f"- Root exists: {str(report['pubscan_profiles']['root_exists']).lower()}",
        f"- Repositories: {report['pubscan_profiles']['repo_count']}",
        f"- Profiled entrypoints: {report['pubscan_profiles']['profiled_entrypoints']}",
        f"- Native-rendering candidates: {report['pubscan_profiles']['native_rendering_candidates']}",
        f"- Native candidate matches: {report['pubscan_profiles']['native_candidate_matches']}",
        f"- Local CPU cores: {report['pubscan_profiles']['local_cpu_cores']}",
        f"- Local GPU status: {report['pubscan_profiles']['local_gpu_status']}",
        f"- Storage roots available: {report['pubscan_profiles']['storage_available_roots']}",
        "",
        "## Endpoint profiles",
        "",
        f"- Profile count: {report['local_models']['profile_count']}",
        f"- Backends: {', '.join(report['local_models']['backends']) or 'none'}",
        f"- Agentic profiles: {report['local_models']['agentic_profiles']}",
        "",
        "## Tool fabric",
        "",
        f"- Tool count: {report['tool_fabric']['tool_count']}",
        f"- Missing roots: {report['tool_fabric']['roots_missing']}",
        "",
        "## Verified facts",
        "",
    ]
    lines.extend(f"- {item}" for item in report["verified_facts"])
    lines.extend(["", "## Assumptions", ""])
    lines.extend(f"- {item}" for item in report["assumptions"])
    lines.extend(["", "## Next gates", ""])
    lines.extend(f"- {item}" for item in report["next_gates"])
    return "\n".join(lines) + "\n"


def _write(path_text: str, text: str) -> None:
    if not path_text:
        return
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _store_outputs(store_root: Path, report: dict[str, Any], markdown: str, run_id: str) -> dict[str, str]:
    if not run_id:
        return {}
    store = FileBackedHarnessStore(store_root)
    json_record = store.write_json(run_id, "harness_architecture_report", report)
    markdown_record = store.write_text(run_id, "harness_architecture_report_md", markdown)
    return {"json": str(json_record.path), "markdown": str(markdown_record.path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", default=str(DEFAULT_DIST))
    parser.add_argument("--release-manifest", default="")
    parser.add_argument("--executable-manifest", default="")
    parser.add_argument("--context-inventory", default="")
    parser.add_argument("--pubscan-profiles", default="")
    parser.add_argument("--endpoint-profiles", default="")
    parser.add_argument("--model-release", default="")
    parser.add_argument("--model-publish", default="")
    parser.add_argument("--tool-contract", default="")
    parser.add_argument("--runtime-contract", default="")
    parser.add_argument("--codex-mcp-contract", default="")
    parser.add_argument("--enterprise-readiness", default="")
    parser.add_argument("--package-doctor", default="")
    parser.add_argument("--store-root", default="C:/tmp/harness_file_store")
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    dist = Path(args.dist)
    report = build_report(
        release_manifest_path=Path(args.release_manifest) if args.release_manifest else dist / "local-harness-release.json",
        executable_manifest_path=Path(args.executable_manifest) if args.executable_manifest else dist / "harness_executable_manifest.local.json",
        context_inventory_path=Path(args.context_inventory) if args.context_inventory else dist / "context_inventory.local.json",
        pubscan_profiles_path=Path(args.pubscan_profiles) if args.pubscan_profiles else dist / "pubscan_resource_profiles.local.json",
        endpoint_profiles_path=Path(args.endpoint_profiles) if args.endpoint_profiles else dist / "model_endpoint_profiles.local.json",
        model_release_path=Path(args.model_release) if args.model_release else dist / "model_release_readiness.local.json",
        model_publish_path=Path(args.model_publish) if args.model_publish else dist / "model_publish_plan.local.json",
        tool_contract_path=Path(args.tool_contract) if args.tool_contract else dist / "tool_integration_contract.local.json",
        runtime_contract_path=Path(args.runtime_contract) if args.runtime_contract else dist / "runtime_activation_contract.local.json",
        codex_mcp_contract_path=Path(args.codex_mcp_contract) if args.codex_mcp_contract else dist / "codex_mcp_launch_contract.local.json",
        enterprise_readiness_path=Path(args.enterprise_readiness) if args.enterprise_readiness else dist / "enterprise_readiness_report.local.json",
        package_doctor_path=Path(args.package_doctor) if args.package_doctor else dist / "packages" / "local-harness-dev-local.doctor.json",
    )
    markdown = render_markdown(report)
    _write(args.out, json.dumps(report, indent=2, sort_keys=True))
    _write(args.markdown_out, markdown)
    store_outputs = _store_outputs(Path(args.store_root), report, markdown, args.run_id)
    result = {**report["summary"], "schema": report["schema"]}
    if store_outputs:
        result["store_outputs"] = store_outputs
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
