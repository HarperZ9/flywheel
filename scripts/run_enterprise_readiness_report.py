"""Emit an enterprise readiness report for packaged sidecar tools."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore

SCHEMA = "harness.enterprise-readiness-report/v1"
DEFAULT_TOOL_CONTRACT = Path("C:/dev/local-model/artifacts/exe/tool_integration_contract.local.json")
DEFAULT_TOOLS = ["mneme", "relay", "plexus"]
ENTERPRISE_CRITERIA = [
    "clear package purpose and positioning",
    "stable CLI and/or MCP entrypoints",
    "tested core workflows",
    "meaningful CI or release gate",
    "install, quickstart, configuration, examples, troubleshooting, and integration docs",
    "explicit security and secret-handling posture",
    "versioned reproducible release artifacts",
    "known limitations and roadmap",
    "ownership, maintenance expectations, and retirement criteria",
]


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _tool_index(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row.get("tool")): row for row in contract.get("tools", []) if isinstance(row, dict)}


def _readiness(tool: dict[str, Any]) -> dict[str, Any]:
    readiness = tool.get("readiness") or {}
    entrypoints = tool.get("entrypoints") or {}
    cli = entrypoints.get("cli") or []
    mcp = entrypoints.get("mcp") or []
    docs_like = tool.get("state_contracts") or []
    score = float(readiness.get("score") or 0.0)
    gates = []
    if not tool.get("root_exists"):
        gates.append("restore or relocate missing tool root before packaging claims")
    if not cli:
        gates.append("publish a stable CLI entrypoint or document why MCP-only is intentional")
    if not mcp:
        gates.append("publish a stable MCP entrypoint or explicit non-MCP interop adapter")
    if score < 0.8:
        gates.append("raise static readiness score to >= 0.80 with docs, tests, CI, examples, and release metadata")
    if score < 1.0:
        gates.append("close remaining enterprise criteria before marking feature-complete")
    if not docs_like:
        gates.append("add state contracts / docs that explain persistence, receipts, limits, and operations")
    if score >= 0.8 and tool.get("root_exists"):
        lane = "RELEASE_CANDIDATE_WITH_GATES"
    elif score >= 0.5 and tool.get("root_exists"):
        lane = "HARDENING_REQUIRED"
    elif tool.get("root_exists"):
        lane = "FOUNDATION_PRESENT"
    else:
        lane = "MISSING_ROOT"
    return {
        "schema": "harness.enterprise-readiness.tool/v1",
        "tool": tool.get("tool"),
        "role": tool.get("role"),
        "root": tool.get("root"),
        "root_exists": bool(tool.get("root_exists")),
        "packaged_mode": tool.get("packaged_mode"),
        "readiness_score": score,
        "readiness_verdict": readiness.get("verdict"),
        "present_total": readiness.get("present_total"),
        "required_total": readiness.get("required_total"),
        "entrypoints": entrypoints,
        "state_contracts": docs_like,
        "release_lane": lane,
        "enterprise_ready": score >= 0.8 and bool(cli or mcp) and bool(tool.get("root_exists")),
        "release_gates": gates,
        "verified_facts": [
            f"root_exists={bool(tool.get('root_exists'))}",
            f"readiness_score={score}",
            f"readiness_verdict={readiness.get('verdict')}",
            f"packaged_mode={tool.get('packaged_mode')}",
        ],
    }


def build_report(*, tool_contract_path: Path, tools: list[str]) -> dict[str, Any]:
    contract = _load(tool_contract_path)
    index = _tool_index(contract)
    selected = []
    missing = []
    for name in tools:
        row = index.get(name)
        if row:
            selected.append(_readiness(row))
        else:
            missing.append(name)
    hardening_required = [row["tool"] for row in selected if not row["enterprise_ready"]]
    return {
        "schema": SCHEMA,
        "created_utc": _now(),
        "tool_contract": {
            "path": str(tool_contract_path),
            "exists": tool_contract_path.exists(),
            "schema": contract.get("schema"),
        },
        "dependency_posture": "metadata-only enterprise readiness report; reads packaged tool contract and does not run benchmarks, providers, endpoints, token stores, source bodies, or tool code",
        "secret_policy": "records tool names, roots, entrypoint names, readiness counts, gates, and receipt contracts only; env values and credentials are not recorded",
        "enterprise_criteria": ENTERPRISE_CRITERIA,
        "tools": selected,
        "missing_tools": missing,
        "reports": {
            "mneme": next((row for row in selected if row["tool"] == "mneme"), None),
            "relay": next((row for row in selected if row["tool"] == "relay"), None),
            "plexus": next((row for row in selected if row["tool"] == "plexus"), None),
        },
        "summary": {
            "tools_requested": len(tools),
            "tools_reported": len(selected),
            "missing_tools": missing,
            "enterprise_ready_count": sum(1 for row in selected if row["enterprise_ready"]),
            "hardening_required": hardening_required,
            "hardening_required_count": len(hardening_required),
            "verdict": "ENTERPRISE_READY" if selected and not hardening_required and not missing else "HARDENING_REQUIRED",
        },
        "next_gates": [
            "Convert each release gate into tracked tool-local issues or checklist rows.",
            "Do not benchmark these tools as enterprise-ready until their readiness reports stop listing hardening gates.",
            "Keep package-doctor and architecture-report green while hardening individual tool repos.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Enterprise readiness report",
        "",
        f"Schema: `{report['schema']}`",
        f"Verdict: **{report['summary']['verdict']}**",
        "",
        "## Tool lanes",
        "",
        "| Tool | Lane | Score | Verdict | Gates |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report["tools"]:
        lines.append(
            f"| {row['tool']} | {row['release_lane']} | {row['readiness_score']:.4f} | "
            f"{row['readiness_verdict']} | {len(row['release_gates'])} |"
        )
    lines.extend(["", "## Enterprise criteria", ""])
    lines.extend(f"- {item}" for item in report["enterprise_criteria"])
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
    json_record = store.write_json(run_id, "enterprise_readiness_report", report)
    markdown_record = store.write_text(run_id, "enterprise_readiness_report_md", markdown)
    return {"json": str(json_record.path), "markdown": str(markdown_record.path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool-contract", default=str(DEFAULT_TOOL_CONTRACT))
    parser.add_argument("--tools", default=",".join(DEFAULT_TOOLS))
    parser.add_argument("--store-root", default="C:/tmp/harness_file_store")
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    tools = [item.strip() for item in args.tools.split(",") if item.strip()]
    report = build_report(tool_contract_path=Path(args.tool_contract), tools=tools)
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
