"""Generate enterprise hardening plans from static tool-readiness receipts."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402


SCHEMA = "harness.tool-hardening-plan/v1"

CATEGORY_OWNERS = {
    "core": "tool-owner",
    "enterprise": "release-engineering",
    "integration": "platform-integration",
}

CATEGORY_PRIORITIES = {
    "core": "P1",
    "enterprise": "P2",
    "integration": "P1",
}

FILE_TASK_HINTS = {
    "SECURITY.md": "Document vulnerability disclosure, secret handling, dependency policy, and supported security boundary.",
    "SUPPORT.md": "Document support channels, version support windows, and escalation expectations.",
    "CONTRIBUTING.md": "Document local setup, test commands, coding standards, and contribution workflow.",
    "CODE_OF_CONDUCT.md": "Document contributor conduct expectations for public release readiness.",
    ".github/dependabot.yml": "Add dependency update policy and scheduled security update checks.",
    ".github/CODEOWNERS": "Assign ownership for source, tests, docs, CI, and release surfaces.",
    ".pre-commit-config.yaml": "Add local formatting, lint, and secret-scan guardrails.",
    ".github/workflows/ci.yml": "Add CI gate for targeted tests, packaging smoke, and static checks.",
    ".github/workflows/release.yml": "Add reproducible release artifact build and publish dry-run gate.",
    "CHANGELOG.md": "Add versioned release notes and compatibility changes.",
    "DELIVERY.md": "Add delivery checklist, artifacts, receipts, and rollback notes.",
    "serve.py": "Add or remove the advertised server entrypoint and document endpoint health behavior.",
}


def now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), ""
    except FileNotFoundError:
        return None, "missing_artifact"
    except (OSError, json.JSONDecodeError) as exc:
        return None, type(exc).__name__


def _priority_for(tool: dict[str, Any], category: str) -> str:
    if not tool.get("root_exists"):
        return "P0"
    return CATEGORY_PRIORITIES.get(category, "P2")


def _task_hint(path_text: str, category: str) -> str:
    return FILE_TASK_HINTS.get(
        path_text,
        f"Add or document `{path_text}` so the `{category}` readiness gate is satisfied.",
    )


def action_items_for_tool(tool: dict[str, Any]) -> list[dict[str, Any]]:
    tool_name = str(tool.get("tool", ""))
    root = str(tool.get("root", ""))
    if not tool.get("root_exists"):
        return [{
            "schema": "harness.tool-hardening-plan.action/v1",
            "tool": tool_name,
            "priority": "P0",
            "category": "core",
            "owner": "tool-owner",
            "path": root,
            "observation": "Tool root is missing.",
            "inference": "The tool cannot be released or integrated until its repository/root is restored or the configured root is corrected.",
            "action": "Restore the tool root or pass the correct --tool-root override before enterprise readiness is evaluated.",
            "acceptance_gate": "Next readiness receipt reports root_exists=true.",
        }]
    actions: list[dict[str, Any]] = []
    categories = tool.get("categories") if isinstance(tool.get("categories"), dict) else {}
    for category, row in categories.items():
        if not isinstance(row, dict):
            continue
        missing = row.get("missing_files") if isinstance(row.get("missing_files"), list) else []
        for path_text in missing:
            path_text = str(path_text)
            actions.append({
                "schema": "harness.tool-hardening-plan.action/v1",
                "tool": tool_name,
                "priority": _priority_for(tool, str(category)),
                "category": str(category),
                "owner": CATEGORY_OWNERS.get(str(category), "tool-owner"),
                "path": path_text,
                "observation": f"`{path_text}` is missing from `{tool_name}` `{category}` readiness requirements.",
                "inference": _task_hint(path_text, str(category)),
                "action": f"Create, restore, or intentionally waive `{path_text}` for `{tool_name}` with a receipt-backed rationale.",
                "acceptance_gate": f"Next readiness receipt lists `{path_text}` under `{category}.present_files`.",
            })
    return actions


def release_gates_for_tool(tool: dict[str, Any], actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tool_name = str(tool.get("tool", ""))
    categories = tool.get("categories") if isinstance(tool.get("categories"), dict) else {}
    gates = []
    for gate_id, category in (
        ("core_static_complete", "core"),
        ("enterprise_static_complete", "enterprise"),
        ("integration_static_complete", "integration"),
    ):
        row = categories.get(category, {}) if isinstance(categories.get(category), dict) else {}
        gates.append({
            "gate_id": gate_id,
            "tool": tool_name,
            "category": category,
            "required": int(row.get("required", 0) or 0),
            "present": int(row.get("present", 0) or 0),
            "passed": float(row.get("score", 0.0) or 0.0) >= 1.0,
            "evidence": "harness.tool-readiness/v1",
        })
    gates.append({
        "gate_id": "all_actions_closed",
        "tool": tool_name,
        "category": "release",
        "required": len(actions),
        "present": 0,
        "passed": len(actions) == 0,
        "evidence": "harness.tool-hardening-plan/v1",
    })
    return gates


def build_plan(
    readiness: dict[str, Any],
    *,
    readiness_artifact: str,
    source_loaded: bool = True,
    source_load_error: str = "",
) -> dict[str, Any]:
    tools = readiness.get("tools") if isinstance(readiness.get("tools"), list) else []
    actions = [
        action
        for tool in tools
        if isinstance(tool, dict)
        for action in action_items_for_tool(tool)
    ]
    gates = [
        gate
        for tool in tools
        if isinstance(tool, dict)
        for gate in release_gates_for_tool(
            tool,
            [action for action in actions if action.get("tool") == tool.get("tool")],
        )
    ]
    priority_counts: dict[str, int] = {}
    owner_counts: dict[str, int] = {}
    for action in actions:
        priority = str(action.get("priority", ""))
        owner = str(action.get("owner", ""))
        priority_counts[priority] = priority_counts.get(priority, 0) + 1
        owner_counts[owner] = owner_counts.get(owner, 0) + 1
    enterprise_ready_static = bool(source_loaded and tools and len(actions) == 0 and gates and all(gate.get("passed") for gate in gates))
    return {
        "schema": SCHEMA,
        "timestamp_utc": now_utc(),
        "source_artifact": readiness_artifact,
        "source_schema": readiness.get("schema", ""),
        "source_loaded": bool(source_loaded),
        "source_load_error": source_load_error,
        "secret_policy": "metadata-only; generated from readiness receipt paths and counts; tool source bodies are not read",
        "tools": [str(tool.get("tool", "")) for tool in tools if isinstance(tool, dict) and tool.get("tool")],
        "actions": actions,
        "release_gates": gates,
        "summary": {
            "tools": len(tools),
            "actions": len(actions),
            "p0_actions": priority_counts.get("P0", 0),
            "p1_actions": priority_counts.get("P1", 0),
            "p2_actions": priority_counts.get("P2", 0),
            "release_gates": len(gates),
            "passed_release_gates": sum(1 for gate in gates if gate.get("passed")),
            "owner_counts": owner_counts,
            "priority_counts": priority_counts,
            "source_loaded": bool(source_loaded),
            "source_load_error": source_load_error,
            "enterprise_ready_static": enterprise_ready_static,
        },
    }


def render_markdown(plan: dict[str, Any]) -> str:
    summary = plan["summary"]
    lines = [
        "# Tool enterprise hardening plan",
        "",
        f"- Schema: `{plan['schema']}`",
        f"- Timestamp UTC: `{plan['timestamp_utc']}`",
        f"- Source artifact: `{plan['source_artifact']}`",
        f"- Source loaded: `{str(plan.get('source_loaded', False)).lower()}`",
        f"- Source load error: `{plan.get('source_load_error', '')}`",
        f"- Secret policy: {plan['secret_policy']}",
        f"- Tools: `{', '.join(plan['tools'])}`",
        f"- Actions: `{summary['actions']}`",
        f"- Release gates passed: `{summary['passed_release_gates']}` / `{summary['release_gates']}`",
        "",
        "## Actions",
        "",
        "| Priority | Tool | Category | Owner | Path | Acceptance gate |",
        "|---|---|---|---|---|---|",
    ]
    for action in plan["actions"]:
        lines.append(
            "| {priority} | {tool} | {category} | {owner} | {path} | {gate} |".format(
                priority=action["priority"],
                tool=action["tool"],
                category=action["category"],
                owner=action["owner"],
                path=action["path"],
                gate=action["acceptance_gate"],
            )
        )
    lines.extend(["", "## Release gates", "", "| Gate | Tool | Category | Passed | Evidence |", "|---|---|---|---:|---|"])
    for gate in plan["release_gates"]:
        lines.append(
            "| {gate_id} | {tool} | {category} | {passed} | {evidence} |".format(
                gate_id=gate["gate_id"],
                tool=gate["tool"],
                category=gate["category"],
                passed=str(gate["passed"]).lower(),
                evidence=gate["evidence"],
            )
        )
    return "\n".join(lines) + "\n"


def write_text(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def store_plan(plan: dict[str, Any], *, store_root: str, run_id: str, artifacts: list[tuple[str, str]]) -> list[dict[str, Any]]:
    if not store_root:
        return []
    store = FileBackedHarnessStore(Path(store_root))
    outputs = [
        store.put_receipt(
            kind="tool_hardening_plan",
            body=plan,
            run_id=run_id,
            verdict=(
                "TOOL_HARDENING_READY"
                if plan["summary"]["enterprise_ready_static"]
                else (
                    "TOOL_HARDENING_UNVERIFIABLE"
                    if not plan["summary"].get("source_loaded")
                    else "TOOL_HARDENING_ACTIONS_OPEN"
                )
            ),
        )
    ]
    for path_text, label in artifacts:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readiness-artifact", required=True)
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    readiness, error = _load_json(Path(args.readiness_artifact))
    if readiness is None:
        readiness = {
            "schema": "",
            "tools": [],
            "load_error": error,
        }
    plan = build_plan(
        readiness,
        readiness_artifact=args.readiness_artifact,
        source_loaded=readiness is not None and not error,
        source_load_error=error,
    )
    if error:
        plan["load_error"] = error
    json_text = json.dumps(plan, indent=2, sort_keys=True)
    md_text = render_markdown(plan)
    json_path = write_text(args.out, json_text)
    md_path = write_text(args.markdown_out, md_text)
    store_outputs = store_plan(
        plan,
        store_root=args.store_root,
        run_id=args.run_id,
        artifacts=[
            (json_path, "tool-hardening-plan-json"),
            (md_path, "tool-hardening-plan-markdown"),
        ],
    )
    if store_outputs:
        plan = {**plan, "store_outputs": store_outputs}
        json_text = json.dumps(plan, indent=2, sort_keys=True)
        write_text(args.out, json_text)
    print(json_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
