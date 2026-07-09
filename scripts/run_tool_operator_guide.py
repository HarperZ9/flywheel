"""Generate a concise operator guide from the packaged tool contract."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCHEMA = "harness.tool-operator-guide/v1"
DEFAULT_CONTRACT = Path("C:/dev/local-model/artifacts/exe/tool_integration_contract.local.json")


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sentence(parts: list[str]) -> str:
    clean = [part.strip().rstrip(".") for part in parts if part and part.strip()]
    return "; ".join(clean) + "." if clean else ""


def _operation_summary(row: dict[str, Any]) -> str:
    commands = (row.get("entrypoints") or {}).get("harness_commands") or []
    cli = (row.get("entrypoints") or {}).get("cli") or []
    mcp = (row.get("entrypoints") or {}).get("mcp") or []
    pieces = []
    if commands:
        pieces.append("Use harness commands " + ", ".join(f"`{item}`" for item in commands))
    if cli:
        pieces.append("direct CLI " + ", ".join(f"`{item}`" for item in cli))
    if mcp:
        pieces.append("MCP server/module " + ", ".join(f"`{item}`" for item in mcp))
    if not pieces:
        pieces.append("Operate through `readiness tools`, `mcp-health`, and `tool-contract` until a direct adapter is promoted")
    return _sentence(pieces)


def _tool_row(row: dict[str, Any]) -> dict[str, Any]:
    readiness = row.get("readiness") or {}
    required_for = row.get("required_for") or []
    return {
        "schema": "harness.tool-operator-guide.tool/v1",
        "tool": str(row.get("tool", "")),
        "role": str(row.get("role", "")),
        "what_it_does": _sentence([", ".join(required_for)]),
        "how_to_operate": _operation_summary(row),
        "packaged_mode": str(row.get("packaged_mode", "")),
        "root": str(row.get("root", "")),
        "root_exists": bool(row.get("root_exists")),
        "state_contracts": row.get("state_contracts") or [],
        "readiness": {
            "verdict": readiness.get("verdict"),
            "score": readiness.get("score"),
            "enterprise_ready": readiness.get("enterprise_ready"),
        },
        "operator_next_action": (
            "Run the listed harness command and inspect emitted receipts before relying on the tool in an agentic workflow."
            if row.get("root_exists")
            else "Restore or configure the tool root, then regenerate tool readiness and hardening receipts."
        ),
    }


def build_guide(contract: dict[str, Any], *, source_contract: Path) -> dict[str, Any]:
    tools = [_tool_row(row) for row in contract.get("tools", []) if isinstance(row, dict)]
    return {
        "schema": SCHEMA,
        "created_utc": _now(),
        "source_contract": str(source_contract),
        "source_schema": contract.get("schema", ""),
        "dependency_posture": "metadata-only guide generated from the tool integration contract; does not run tools or read source bodies",
        "secret_policy": "records non-secret roles, commands, roots, readiness verdicts, and operator next actions only",
        "tools": tools,
        "summary": {
            "tools": len(tools),
            "roots_existing": sum(1 for row in tools if row["root_exists"]),
            "enterprise_ready": sum(1 for row in tools if row["readiness"].get("enterprise_ready")),
            "sidecar_tools": sum(1 for row in tools if row["packaged_mode"] == "external_repo_sidecar"),
            "bundled_core_tools": sum(1 for row in tools if row["packaged_mode"] != "external_repo_sidecar"),
        },
    }


def render_markdown(guide: dict[str, Any]) -> str:
    summary = guide["summary"]
    lines = [
        "# Tool operator guide",
        "",
        f"- Schema: `{guide['schema']}`",
        f"- Source contract: `{guide['source_contract']}`",
        f"- Tools: `{summary['tools']}`",
        f"- Roots existing: `{summary['roots_existing']}`",
        f"- Enterprise-ready static tools: `{summary['enterprise_ready']}`",
        "",
        "| Tool | What it does | How to operate | Readiness | Next action |",
        "|---|---|---|---|---|",
    ]
    for row in guide["tools"]:
        readiness = row["readiness"]
        lines.append(
            "| {tool} | {what} | {how} | {verdict} ({score}) | {next_action} |".format(
                tool=row["tool"],
                what=row["what_it_does"],
                how=row["how_to_operate"],
                verdict=readiness.get("verdict"),
                score=readiness.get("score"),
                next_action=row["operator_next_action"],
            )
        )
    lines.extend([
        "",
        "This guide is concise by design. The authoritative machine contract remains the packaged `tool_integration_contract.local.json` artifact.",
    ])
    return "\n".join(lines) + "\n"


def _write(path_text: str, text: str) -> None:
    if not path_text:
        return
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool-contract", default=str(DEFAULT_CONTRACT))
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    args = parser.parse_args(argv)

    source = Path(args.tool_contract)
    guide = build_guide(_load_json(source), source_contract=source)
    markdown = render_markdown(guide)
    _write(args.out, json.dumps(guide, indent=2, sort_keys=True))
    _write(args.markdown_out, markdown)
    print(json.dumps({**guide["summary"], "schema": guide["schema"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
