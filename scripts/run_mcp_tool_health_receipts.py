"""Emit metadata-only MCP/tool health receipts for closed-loop runs.

The command does not call MCP servers. It records configured tool roots plus
optional observations gathered by the operator/agent in the current session so
tool health can be compared across benchmark runs without reading secrets or
probing providers.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402


DEFAULT_TOOLS: dict[str, dict[str, str]] = {
    "index": {"role": "structure-context", "root": "C:/dev/public/index"},
    "forum": {"role": "orchestration-routing", "root": "C:/dev/public/forum"},
    "telos": {"role": "shared-room-reconciliation", "root": "C:/dev/public/telos"},
    "gather": {"role": "perception-intake", "root": "C:/dev/public/gather"},
    "crucible": {"role": "verification-pressure", "root": "C:/dev/public/crucible"},
    "aleph": {"role": "research-memory", "root": "C:/dev/aleph"},
    "mneme": {"role": "memory-provenance", "root": "C:/dev/public/mneme"},
    "relay": {"role": "event-transport", "root": "C:/dev/public/relay"},
    "plexus": {"role": "planning-routing", "root": "C:/dev/public/plexus"},
    "pubscan": {"role": "public-scan-tooling", "root": "C:/dev/public/pubscan"},
    "local-model": {"role": "benchmark-harness", "root": "C:/dev/local-model"},
}

HEALTHY_STATUSES = {"MATCH", "OK", "READY", "CALLABLE", "HEALTHY"}
DEGRADED_STATUSES = {"TRANSPORT_CLOSED", "ERROR", "FAILED", "TIMEOUT", "UNVERIFIABLE", "DEGRADED"}


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def split_names(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_observations(values: list[str]) -> dict[str, dict[str, Any]]:
    observations: dict[str, dict[str, Any]] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"--observation expects name=status|error|summary, got {value!r}")
        name, payload = value.split("=", 1)
        parts = payload.split("|", 2)
        status = parts[0].strip()
        observations[name.strip()] = {
            "status": status,
            "error_code": parts[1].strip() if len(parts) > 1 else "",
            "summary": parts[2].strip() if len(parts) > 2 else "",
        }
    return observations


def classify(*, root_exists: bool, observed_status: str) -> str:
    normalized = observed_status.strip().upper()
    if normalized in HEALTHY_STATUSES:
        return "OBSERVED_HEALTHY"
    if normalized in DEGRADED_STATUSES:
        return "OBSERVED_DEGRADED"
    if observed_status:
        return "OBSERVED_UNKNOWN"
    if root_exists:
        return "CONFIGURED_UNOBSERVED"
    return "MISSING_ROOT"


def tool_row(*, tool: str, profile: dict[str, str], observation: dict[str, Any]) -> dict[str, Any]:
    root = Path(profile.get("root", ""))
    root_exists = root.exists()
    observed_status = str(observation.get("status", ""))
    verdict = classify(root_exists=root_exists, observed_status=observed_status)
    return {
        "schema": "harness.mcp-tool-health.tool/v1",
        "tool": tool,
        "role": profile.get("role", ""),
        "root": str(root),
        "root_exists": root_exists,
        "observed": bool(observed_status),
        "observed_status": observed_status,
        "observed_error_code": str(observation.get("error_code", "")),
        "observed_summary": str(observation.get("summary", "")),
        "verdict": verdict,
        "provider_execution_observed": False,
        "endpoint_probe_observed": False,
        "secret_policy": "metadata-only root existence and non-secret status labels",
    }


def build_report(*, tools: list[str], observations: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = [
        tool_row(
            tool=tool,
            profile=DEFAULT_TOOLS.get(tool, {"role": "custom", "root": ""}),
            observation=observations.get(tool, {}),
        )
        for tool in tools
    ]
    verdict_counts: dict[str, int] = {}
    for row in rows:
        verdict = str(row["verdict"])
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
    return {
        "schema": "harness.mcp-tool-health/v1",
        "created_utc": utc_now(),
        "dependency_posture": "metadata-only; does not call MCP servers, providers, endpoints, token stores, or model weights",
        "tools": rows,
        "summary": {
            "tools": len(rows),
            "roots_existing": sum(1 for row in rows if row["root_exists"]),
            "observed_tools": sum(1 for row in rows if row["observed"]),
            "healthy_observed_tools": verdict_counts.get("OBSERVED_HEALTHY", 0),
            "degraded_observed_tools": verdict_counts.get("OBSERVED_DEGRADED", 0),
            "configured_unobserved_tools": verdict_counts.get("CONFIGURED_UNOBSERVED", 0),
            "missing_roots": verdict_counts.get("MISSING_ROOT", 0),
            "verdict_counts": verdict_counts,
            "degraded_tools": sorted(row["tool"] for row in rows if row["verdict"] == "OBSERVED_DEGRADED"),
            "healthy_tools": sorted(row["tool"] for row in rows if row["verdict"] == "OBSERVED_HEALTHY"),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# MCP tool health receipts",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Created UTC: `{report['created_utc']}`",
        f"- Dependency posture: {report['dependency_posture']}",
        f"- Tools: `{summary['tools']}`",
        f"- Existing roots: `{summary['roots_existing']}`",
        f"- Observed tools: `{summary['observed_tools']}`",
        f"- Healthy observed tools: `{summary['healthy_observed_tools']}`",
        f"- Degraded observed tools: `{summary['degraded_observed_tools']}`",
        "",
        "| Tool | Role | Verdict | Root exists | Observed status | Error code |",
        "|---|---|---|---:|---|---|",
    ]
    for row in report["tools"]:
        lines.append(
            "| {tool} | {role} | {verdict} | {root_exists} | {status} | {error} |".format(
                tool=row["tool"],
                role=row["role"],
                verdict=row["verdict"],
                root_exists=str(row["root_exists"]).lower(),
                status=row["observed_status"],
                error=row["observed_error_code"],
            )
        )
    return "\n".join(lines) + "\n"


def _write(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def _store_outputs(report: dict[str, Any], *, store_root: str, run_id: str, artifacts: list[tuple[str, str]]) -> list[dict[str, Any]]:
    if not store_root:
        return []
    store = FileBackedHarnessStore(Path(store_root))
    verdict = "MCP_TOOL_HEALTH_DEGRADED" if report["summary"]["degraded_observed_tools"] else "MCP_TOOL_HEALTH_RECORDED"
    outputs = [store.put_receipt(kind="mcp_tool_health", body=report, run_id=run_id, verdict=verdict)]
    for path_text, label in artifacts:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools", default="index,forum,telos,gather,crucible,aleph,mneme,relay,plexus,pubscan,local-model")
    parser.add_argument("--observation", action="append", default=[], help="name=status|error_code|summary")
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    report = build_report(
        tools=split_names(args.tools),
        observations=parse_observations(args.observation),
    )
    json_text = json.dumps(report, indent=2, sort_keys=True)
    md_text = render_markdown(report)
    json_path = _write(args.out, json_text)
    md_path = _write(args.markdown_out, md_text)
    store_outputs = _store_outputs(
        report,
        store_root=args.store_root,
        run_id=args.run_id,
        artifacts=[
            (json_path, "mcp-tool-health-json"),
            (md_path, "mcp-tool-health-markdown"),
        ],
    )
    if store_outputs:
        report = {**report, "store_outputs": store_outputs}
        json_text = json.dumps(report, indent=2, sort_keys=True)
    print(json_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
