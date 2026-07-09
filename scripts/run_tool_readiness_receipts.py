"""Emit static enterprise-readiness receipts for flagship local tools.

This command records file/path metadata only. It does not run tool tests,
execute CLIs, read source file bodies, or copy scanned tool source into the
store. It is a low-cost readiness preflight for mneme, relay, and plexus.
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


TOOL_PROFILES: dict[str, dict[str, list[str]]] = {
    "mneme": {
        "core": [
            "pyproject.toml",
            "README.md",
            "src/mneme",
            "tests",
            "src/mneme/store.py",
            "src/mneme/drift.py",
            "src/mneme/receipt.py",
            "src/mneme/mcp.py",
        ],
        "enterprise": [
            "SECURITY.md",
            "SUPPORT.md",
            "CONTRIBUTING.md",
            "CODE_OF_CONDUCT.md",
            ".github/dependabot.yml",
            ".github/CODEOWNERS",
            ".pre-commit-config.yaml",
            "src/mneme/py.typed",
        ],
        "integration": [
            ".github/workflows/ci.yml",
            ".github/workflows/release.yml",
            "CHANGELOG.md",
            "DELIVERY.md",
        ],
    },
    "relay": {
        "core": [
            "pyproject.toml",
            "README.md",
            "src/relay",
            "tests",
        ],
        "enterprise": [
            "SECURITY.md",
            "SUPPORT.md",
            "CONTRIBUTING.md",
            "CODE_OF_CONDUCT.md",
            ".github/dependabot.yml",
            ".github/CODEOWNERS",
            ".pre-commit-config.yaml",
            "src/relay/py.typed",
        ],
        "integration": [
            ".github/workflows/ci.yml",
            ".github/workflows/release.yml",
            "docs/claude-code.md",
            "docs/opencode.md",
            "docs/codex.md",
            "serve.py",
        ],
    },
    "plexus": {
        "core": [
            "pyproject.toml",
            "README.md",
            "src/plexus",
            "tests",
        ],
        "enterprise": [
            "SECURITY.md",
            "SUPPORT.md",
            "CONTRIBUTING.md",
            "CODE_OF_CONDUCT.md",
            ".github/dependabot.yml",
            ".github/CODEOWNERS",
            ".pre-commit-config.yaml",
            "src/plexus/py.typed",
        ],
        "integration": [
            ".github/workflows/ci.yml",
            ".github/workflows/release.yml",
            "src/plexus/grounding.py",
            "src/plexus/benchmark.py",
            "docs/api.md",
        ],
    },
}


def now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def split_names(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _exists(root: Path, rel: str) -> bool:
    return (root / rel).exists()


def _category(root: Path, rels: list[str]) -> dict[str, Any]:
    present = [rel for rel in rels if _exists(root, rel)]
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


def _verdict(root_exists: bool, categories: dict[str, dict[str, Any]]) -> str:
    if not root_exists:
        return "TOOL_MISSING"
    core_score = float(categories["core"]["score"])
    all_score = min(float(row["score"]) for row in categories.values())
    if all_score >= 1.0:
        return "ENTERPRISE_READY_STATIC"
    if core_score >= 0.75:
        return "PROTOTYPE_WITH_GAPS"
    return "INCOMPLETE_STATIC"


def profile_tool(tool: str, root: Path) -> dict[str, Any]:
    profile = TOOL_PROFILES.get(tool, {"core": ["pyproject.toml", "README.md"], "enterprise": [], "integration": []})
    root = root.expanduser()
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
        for name, rels in profile.items()
    }
    required_total = sum(row["required"] for row in categories.values())
    present_total = sum(row["present"] for row in categories.values())
    verdict = _verdict(root_exists, categories)
    return {
        "tool": tool,
        "root": str(root),
        "root_exists": root_exists,
        "schema": "harness.tool-readiness.tool/v1",
        "content_read": False,
        "categories": categories,
        "required_total": required_total,
        "present_total": present_total,
        "score": round(present_total / required_total, 4) if required_total else 1.0,
        "enterprise_ready": verdict == "ENTERPRISE_READY_STATIC",
        "verdict": verdict,
    }


def build_report(*, tools: list[str], base_root: Path, explicit_roots: dict[str, Path]) -> dict[str, Any]:
    rows = []
    for tool in tools:
        root = explicit_roots.get(tool, base_root / tool)
        rows.append(profile_tool(tool, root))
    verdict_counts: dict[str, int] = {}
    for row in rows:
        verdict = str(row["verdict"])
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
    return {
        "schema": "harness.tool-readiness/v1",
        "timestamp_utc": now_utc(),
        "secret_policy": "metadata-only; tool source bodies are not read; generated readiness artifacts only are stored",
        "base_root": str(base_root),
        "tools": rows,
        "summary": {
            "tools": len(rows),
            "existing_tools": sum(1 for row in rows if row["root_exists"]),
            "missing_tools": sum(1 for row in rows if not row["root_exists"]),
            "enterprise_ready_tools": sum(1 for row in rows if row["enterprise_ready"]),
            "prototype_with_gaps": verdict_counts.get("PROTOTYPE_WITH_GAPS", 0),
            "verdict_counts": verdict_counts,
            "mean_score": round(sum(float(row["score"]) for row in rows) / len(rows), 4) if rows else 0.0,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Tool readiness receipt",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Timestamp UTC: `{report['timestamp_utc']}`",
        f"- Secret policy: {report['secret_policy']}",
        f"- Existing tools: `{summary['existing_tools']}` / `{summary['tools']}`",
        f"- Enterprise-ready static tools: `{summary['enterprise_ready_tools']}`",
        f"- Mean static score: `{summary['mean_score']}`",
        "",
        "| Tool | Verdict | Score | Core | Enterprise | Integration |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in report["tools"]:
        categories = row["categories"]
        lines.append(
            "| {tool} | {verdict} | {score} | {core} | {enterprise} | {integration} |".format(
                tool=row["tool"],
                verdict=row["verdict"],
                score=row["score"],
                core=categories.get("core", {}).get("score", 0.0),
                enterprise=categories.get("enterprise", {}).get("score", 0.0),
                integration=categories.get("integration", {}).get("score", 0.0),
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


def _parse_roots(values: list[str]) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"--tool-root expects name=path, got {value!r}")
        name, path = value.split("=", 1)
        roots[name.strip()] = Path(path.strip())
    return roots


def _store_outputs(report: dict[str, Any], *, store_root: str, run_id: str, artifacts: list[tuple[str, str]]) -> list[dict[str, Any]]:
    if not store_root:
        return []
    store = FileBackedHarnessStore(Path(store_root))
    outputs = [
        store.put_receipt(
            kind="tool_readiness",
            body=report,
            run_id=run_id,
            verdict="TOOL_READINESS_FULL"
            if report["summary"]["enterprise_ready_tools"] == report["summary"]["tools"]
            else "TOOL_READINESS_PARTIAL",
        )
    ]
    for path_text, label in artifacts:
        if path_text and Path(path_text).exists():
            outputs.append(store.copy_artifact(Path(path_text), run_id=run_id, label=label))
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools", default="mneme,relay,plexus")
    parser.add_argument("--base-root", default="C:/dev/public")
    parser.add_argument("--tool-root", action="append", default=[], help="override a tool root as name=path")
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--store-root", default="")
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)

    report = build_report(
        tools=split_names(args.tools),
        base_root=Path(args.base_root),
        explicit_roots=_parse_roots(args.tool_root),
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
            (json_path, "tool-readiness-json"),
            (md_path, "tool-readiness-markdown"),
        ],
    )
    if store_outputs:
        report = {**report, "store_outputs": store_outputs}
        json_text = json.dumps(report, indent=2, sort_keys=True)
    print(json_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
