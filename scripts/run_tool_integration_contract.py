"""Emit the packaged integration contract for Flywheel/Codex local tools."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402
from run_mcp_tool_health_receipts import DEFAULT_TOOLS as MCP_TOOLS  # noqa: E402
from run_tool_readiness_receipts import profile_tool, split_names  # noqa: E402

DEFAULT_TOOL_SET = "index,forum,gather,crucible,telos,aleph,mneme,relay,plexus,pubscan,local-model"

INTERFACES: dict[str, dict[str, Any]] = {
    "index": {
        "packaged_mode": "external_repo_sidecar",
        "cli": ["python -m index_graph.cli"],
        "mcp": ["index_graph.mcp"],
        "harness_commands": ["mcp-health", "readiness tools", "tool-contract"],
        "state_contracts": ["metadata root map", "context-envelope fallback receipt", "workspace structure map"],
        "required_for": ["workspace context map", "repository navigation", "architecture evidence"],
    },
    "forum": {
        "packaged_mode": "external_repo_sidecar",
        "cli": ["python -m forum.cli"],
        "mcp": [],
        "harness_commands": ["forum-route", "mcp-health", "tool-contract"],
        "state_contracts": ["route receipt", "causal ledger handoff", "operator routing decision"],
        "required_for": ["ambiguous work routing", "closed-loop orchestration", "ledger accountability"],
    },
    "gather": {
        "packaged_mode": "external_repo_sidecar",
        "cli": [],
        "mcp": ["gather.mcp"],
        "harness_commands": ["readiness gather", "mcp-health", "tool-contract"],
        "state_contracts": ["source intake receipt", "credential presence booleans", "capture config profile"],
        "required_for": ["source intake", "research mining", "feedback-loop ingestion"],
    },
    "crucible": {
        "packaged_mode": "external_repo_sidecar",
        "cli": [],
        "mcp": ["crucible.mcp"],
        "harness_commands": ["readiness tools", "tool-hardening", "tool-contract"],
        "state_contracts": ["verification pressure receipt", "claim check handoff"],
        "required_for": ["claim verification", "artifact pressure testing"],
    },
    "telos": {
        "packaged_mode": "external_repo_sidecar",
        "cli": [],
        "mcp": ["telos.mcp"],
        "harness_commands": ["readiness tools", "mcp-health", "tool-contract"],
        "state_contracts": ["shared-room reconciliation", "goal state contract"],
        "required_for": ["goal routing", "shared state reconciliation"],
    },
    "aleph": {
        "packaged_mode": "external_repo_sidecar",
        "cli": [],
        "mcp": [],
        "harness_commands": ["readiness tools", "mcp-health", "tool-contract"],
        "state_contracts": ["research memory handoff", "knowledge reference pointer"],
        "required_for": ["research memory", "source synthesis"],
    },
    "mneme": {
        "packaged_mode": "external_repo_sidecar",
        "cli": [],
        "mcp": ["mneme.mcp"],
        "harness_commands": ["readiness tools", "tool-hardening", "tool-contract"],
        "state_contracts": ["memory provenance receipt", "drift record", "store contract"],
        "required_for": ["memory provenance", "long-horizon continuity"],
    },
    "relay": {
        "packaged_mode": "external_repo_sidecar",
        "cli": ["python serve.py"],
        "mcp": [],
        "harness_commands": ["readiness tools", "tool-hardening", "tool-contract"],
        "state_contracts": ["event transport envelope", "Codex/Claude/OpenCode bridge docs"],
        "required_for": ["harness interop", "event transport", "agent bridge"],
    },
    "plexus": {
        "packaged_mode": "external_repo_sidecar",
        "cli": [],
        "mcp": [],
        "harness_commands": ["readiness tools", "tool-hardening", "tool-contract"],
        "state_contracts": ["planning route graph", "grounding record", "benchmark contract"],
        "required_for": ["planning router", "grounded execution", "tool selection"],
    },
    "pubscan": {
        "packaged_mode": "external_repo_sidecar",
        "cli": [],
        "mcp": [],
        "harness_commands": ["readiness pubscan", "readiness tools", "tool-contract"],
        "state_contracts": ["public repo profile", "native-rendering resource profile", "zero-dependency scan profile"],
        "required_for": ["pubscan tool import", "buildlang/buildc corpus location", "native rendering architecture"],
    },
    "local-model": {
        "packaged_mode": "bundled_core_plus_external_model_runtime",
        "cli": ["bin/local-harness.cmd", "bin/local-agent.exe"],
        "mcp": [],
        "harness_commands": ["manifest", "registry", "serve-launch", "serve-resource", "endpoint-launch-readiness"],
        "state_contracts": ["file-backed harness store", "local endpoint profile", "release bundle manifest"],
        "required_for": ["packaged harness", "local model endpoint routing", "release artifact generation"],
    },
}

LOCAL_MODEL_PROFILE = {
    "core": ["harness", "scripts/run_harness_cli.py", "scripts/local_harness_entry.py", "harness.cmd"],
    "enterprise": ["project-docs/HARNESS-PACKAGING.md", ".gitignore"],
    "integration": [
        "scripts/build_local_harness_exes.py",
        "scripts/package_local_harness_release.py",
        "scripts/run_model_endpoint_profiles.py",
    ],
}


def now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _parse_roots(values: list[str]) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"--tool-root expects name=path, got {value!r}")
        name, path = value.split("=", 1)
        roots[name.strip()] = Path(path.strip())
    return roots


def _category(root: Path, rels: list[str]) -> dict[str, Any]:
    present = [rel for rel in rels if (root / rel).exists()]
    missing = [rel for rel in rels if rel not in present]
    total = len(rels)
    return {
        "required": total,
        "present": len(present),
        "missing": len(missing),
        "score": round(len(present) / total, 4) if total else 1.0,
        "present_files": present,
        "missing_files": missing,
    }


def _local_model_readiness(root: Path) -> dict[str, Any]:
    root_exists = root.exists()
    categories = {
        name: _category(root, rels) if root_exists else {
            "required": len(rels),
            "present": 0,
            "missing": len(rels),
            "score": 0.0,
            "present_files": [],
            "missing_files": rels,
        }
        for name, rels in LOCAL_MODEL_PROFILE.items()
    }
    required_total = sum(row["required"] for row in categories.values())
    present_total = sum(row["present"] for row in categories.values())
    enterprise_ready = root_exists and present_total == required_total
    return {
        "tool": "local-model",
        "root": str(root),
        "root_exists": root_exists,
        "schema": "harness.tool-readiness.tool/v1",
        "content_read": False,
        "categories": categories,
        "required_total": required_total,
        "present_total": present_total,
        "score": round(present_total / required_total, 4) if required_total else 1.0,
        "enterprise_ready": enterprise_ready,
        "verdict": "ENTERPRISE_READY_STATIC" if enterprise_ready else "PROTOTYPE_WITH_GAPS",
    }


def readiness_for(tool: str, root: Path) -> dict[str, Any]:
    if tool == "local-model":
        return _local_model_readiness(root)
    return profile_tool(tool, root)


def tool_root(tool: str, *, base_root: Path, explicit_roots: dict[str, Path]) -> Path:
    if tool in explicit_roots:
        return explicit_roots[tool]
    default = MCP_TOOLS.get(tool, {}).get("root")
    if default:
        return Path(default)
    return base_root / tool


def contract_row(tool: str, *, base_root: Path, explicit_roots: dict[str, Path], package_root: Path) -> dict[str, Any]:
    root = tool_root(tool, base_root=base_root, explicit_roots=explicit_roots)
    readiness = readiness_for(tool, root)
    interface = INTERFACES.get(tool, {
        "packaged_mode": "external_repo_sidecar",
        "cli": [],
        "mcp": [],
        "harness_commands": ["readiness tools", "tool-contract"],
        "state_contracts": ["metadata-only root contract"],
        "required_for": ["custom tool integration"],
    })
    role = MCP_TOOLS.get(tool, {}).get("role", "custom")
    return {
        "schema": "harness.tool-integration-contract.tool/v1",
        "tool": tool,
        "role": role,
        "root": str(root),
        "root_exists": bool(readiness["root_exists"]),
        "packaged_mode": interface["packaged_mode"],
        "package_root": str(package_root),
        "entrypoints": {
            "cli": interface["cli"],
            "mcp": interface["mcp"],
            "harness_commands": interface["harness_commands"],
        },
        "state_contracts": interface["state_contracts"],
        "required_for": interface["required_for"],
        "readiness": {
            "verdict": readiness["verdict"],
            "score": readiness["score"],
            "enterprise_ready": readiness["enterprise_ready"],
            "required_total": readiness["required_total"],
            "present_total": readiness["present_total"],
        },
        "activation": {
            "secret_policy": "do not package secrets; expose only root paths, command names, booleans, hashes, and receipts",
            "runtime_binding": "external repo/tool sidecar unless packaged_mode is bundled_core_plus_external_model_runtime",
            "failure_policy": "missing roots or degraded observations produce receipts and hardening actions, not silent fallback",
        },
        "ship_status": "wired_root_present" if readiness["root_exists"] else "wired_root_missing",
    }


def build_contract(*, tools: list[str], base_root: Path, explicit_roots: dict[str, Path], package_root: Path) -> dict[str, Any]:
    rows = [
        contract_row(tool, base_root=base_root, explicit_roots=explicit_roots, package_root=package_root)
        for tool in tools
    ]
    return {
        "schema": "harness.tool-integration-contract/v1",
        "created_utc": now_utc(),
        "base_root": str(base_root),
        "package_root": str(package_root),
        "dependency_posture": "metadata-only architecture contract; does not call tools, providers, endpoints, token stores, or model weights",
        "secret_policy": "tool source bodies, .env values, credentials, tokens, private keys, and model weights are not read or packaged",
        "tools": rows,
        "summary": {
            "tools": len(rows),
            "roots_existing": sum(1 for row in rows if row["root_exists"]),
            "roots_missing": sum(1 for row in rows if not row["root_exists"]),
            "enterprise_ready_static": sum(1 for row in rows if row["readiness"]["enterprise_ready"]),
            "sidecar_tools": sum(1 for row in rows if row["packaged_mode"] == "external_repo_sidecar"),
            "bundled_core_tools": sum(1 for row in rows if row["packaged_mode"] != "external_repo_sidecar"),
        },
    }


def render_markdown(contract: dict[str, Any]) -> str:
    summary = contract["summary"]
    lines = [
        "# Tool integration contract",
        "",
        f"- Schema: `{contract['schema']}`",
        f"- Created UTC: `{contract['created_utc']}`",
        f"- Dependency posture: {contract['dependency_posture']}",
        f"- Secret policy: {contract['secret_policy']}",
        f"- Roots existing: `{summary['roots_existing']}` / `{summary['tools']}`",
        f"- Bundled core tools: `{summary['bundled_core_tools']}`",
        f"- Sidecar tools: `{summary['sidecar_tools']}`",
        "",
        "| Tool | Role | Mode | Root exists | Readiness | Harness commands |",
        "|---|---|---|---:|---|---|",
    ]
    for row in contract["tools"]:
        commands = ", ".join(row["entrypoints"]["harness_commands"])
        lines.append(
            f"| {row['tool']} | {row['role']} | {row['packaged_mode']} | {str(row['root_exists']).lower()} | "
            f"{row['readiness']['verdict']} ({row['readiness']['score']}) | {commands} |"
        )
    return "\n".join(lines) + "\n"


def _write(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def _store_outputs(contract: dict[str, Any], *, store_root: str, run_id: str, artifacts: list[tuple[str, str]]) -> list[dict[str, Any]]:
    if not store_root:
        return []
    store = FileBackedHarnessStore(Path(store_root))
    verdict = "TOOL_CONTRACT_PARTIAL" if contract["summary"]["roots_missing"] else "TOOL_CONTRACT_WIRED"
    outputs = [store.put_receipt(kind="tool_integration_contract", body=contract, run_id=run_id, verdict=verdict)]
    for path_text, label in artifacts:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools", default=DEFAULT_TOOL_SET)
    parser.add_argument("--base-root", default="C:/dev/public")
    parser.add_argument("--tool-root", action="append", default=[], help="override a tool root as name=path")
    parser.add_argument("--package-root", default="C:/dev/local-model/artifacts/exe")
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    contract = build_contract(
        tools=split_names(args.tools),
        base_root=Path(args.base_root),
        explicit_roots=_parse_roots(args.tool_root),
        package_root=Path(args.package_root),
    )
    json_text = json.dumps(contract, indent=2, sort_keys=True)
    md_text = render_markdown(contract)
    json_path = _write(args.out, json_text)
    md_path = _write(args.markdown_out, md_text)
    store_outputs = _store_outputs(
        contract,
        store_root=args.store_root,
        run_id=args.run_id,
        artifacts=[
            (json_path, "tool-integration-contract-json"),
            (md_path, "tool-integration-contract-markdown"),
        ],
    )
    if store_outputs:
        contract = {**contract, "store_outputs": store_outputs}
        json_text = json.dumps(contract, indent=2, sort_keys=True)
    print(json_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
