"""Validate a sealed agt-003 cross-harness run without running providers."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.cross_harness_postrun import validate_postrun_comparison  # noqa: E402

def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Cross-harness post-run comparison",
        "",
        f"- Schema: `{report.get('schema', '')}`",
        f"- Decision: `{report.get('decision', '')}`",
        f"- Comparison scope: `{report.get('comparison_scope', '')}`",
        f"- Quality ranking: `{report.get('quality_ranking')}`",
        f"- Reasons: `{', '.join(report.get('reasons', []))}`",
        f"- Counts: `{json.dumps(report.get('counts', {}), sort_keys=True)}`",
        f"- Enforcement equivalence: `{(report.get('enforcement') or {}).get('equivalence', 'unknown')}`",
        "",
        "This validator reads local run artifacts only and does not run providers.",
        "",
        "## Cells",
        "",
        "| Role | Task | Rep | State | Execution | Oracle | Outcome | Reasons |",
        "|---|---|---:|---|---|---|---|---|",
    ]
    for cell in report.get("cells", []):
        lines.append("| {role} | {task} | {rep} | {state} | {execution} | {oracle} | {outcome} | {reasons} |".format(
            role=cell.get("provider_role", ""), task=cell.get("task_id", ""), rep=cell.get("repetition", ""),
            state=cell.get("state", ""), execution=cell.get("execution_state", ""), oracle=cell.get("oracle_state", ""),
            outcome=cell.get("primary_outcome", ""), reasons=", ".join(cell.get("reasons", []))))
    lines.extend(["", "## Does not prove", ""])
    for item in report.get("does_not_prove", []):
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"

def _write(path_text: str, text: str) -> None:
    if path_text:
        path = Path(path_text)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_root")
    parser.add_argument("--out", default="")
    parser.add_argument("--markdown-out", default="")
    args = parser.parse_args(argv)
    report = validate_postrun_comparison(args.run_root)
    _write(args.out, json.dumps(report, indent=2, sort_keys=True) + "\n")
    _write(args.markdown_out, render_markdown(report))
    if not args.out and not args.markdown_out:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("decision") == "completed_comparison" else 3

if __name__ == "__main__":
    raise SystemExit(main())
