"""Score every oracle checker against candidates that did not do the task.

A benchmark reports a pass rate. That rate is a measurement only if something
exists that ought to fail it. This drives each configured checker with three
ways of not answering and writes what each one scored.

The cases come from the test suite on purpose. They are the same synthetic
fixtures the oracle tests check, and a second copy under harness/ would let the
measured floor drift away from the cases the suite actually exercises.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from harness.cross_harness_null_adapters import (  # noqa: E402
    BREACHED, STRATEGIES, build_null_floor_report, rejected_at, write_null_submission,
)
from harness.cross_harness_oracles import OracleContext, evaluate_task_oracle  # noqa: E402
from harness.file_backed_store import FileBackedHarnessStore  # noqa: E402


def build_case(tmp_path: Path, checker: str):
    from test_cross_harness_oracles import _case
    from test_oracle_documentation_v2 import CHECKER_ID, case_v2

    return case_v2(tmp_path) if checker == CHECKER_ID else _case(tmp_path, checker)


def checker_ids() -> list[str]:
    from harness.cross_harness_oracles import _CHECKERS

    return sorted(_CHECKERS)


def score(tmp_path: Path, checker: str, strategy: str) -> dict:
    """The good case with only the submission swapped for one that did not answer."""
    context, report, fixture = build_case(tmp_path, checker)
    submission = write_null_submission(
        context.raw_output_path.parent, strategy=strategy, task_id=context.task_id,
        template=report, fixture=fixture, expected_artifacts=tuple(context.artifact_paths))
    swapped = OracleContext(context.task_id, context.oracle_spec, submission.raw_output_path,
                            submission.artifact_paths, context.expected_input_sha256s,
                            context.scorecard_core)
    result = evaluate_task_oracle(swapped)
    reason = str((result.evidence or {}).get("reason", ""))
    return {"checker_id": checker, "strategy": strategy, "oracle_state": result.state,
            "failure_codes": sorted(result.failure_codes), "reason": reason,
            "rejected_at": rejected_at(result.failure_codes, reason),
            "rejected": result.state in ("fail", "malformed", "unverifiable")}


def render_markdown(report: dict) -> str:
    denominator = report["denominator"]
    lines = [f"# Null floor: {report['verdict']}", "",
             f"{denominator['candidates']} candidates, {denominator['checkers']} checkers, "
             f"{denominator['strategies']} strategies, "
             f"{denominator['checkers_reached']} checkers reached by at least one candidate.",
             "", "| checker | strategy | state | rejected at | codes |",
             "| --- | --- | --- | --- | --- |"]
    for row in report["rows"]:
        codes = ", ".join(row["failure_codes"]) or "none"
        lines.append(f"| {row['checker_id']} | {row['strategy']} | {row['oracle_state']} "
                     f"| {row['rejected_at']} | {codes} |")
    if report["breaches"]:
        lines += ["", "## Breaches", ""]
        lines += [f"- {row['checker_id']} scored the {row['strategy']} candidate "
                  f"{row['oracle_state']}" for row in report["breaches"]]
    if report["checkers_never_reached"]:
        lines += ["", "## Never reached", ""]
        lines += [f"- {name}" for name in report["checkers_never_reached"]]
    lines += ["", "## What this does not prove", ""]
    lines += [f"- {item}" for item in report["does_not_prove"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="", help="path for the JSON report")
    parser.add_argument("--markdown-out", default="", help="path for the table")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--store-root", default="", help="receipt store the verdict is filed in")
    parser.add_argument("--fail-on-breach", action="store_true",
                        help="exit non-zero when a checker passes a candidate that did not answer")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as staging:
        rows = [score(Path(staging) / checker.replace("/", "-") / strategy, checker, strategy)
                for checker in checker_ids() for strategy in STRATEGIES]
    report = build_null_floor_report(rows, run_id=args.run_id)
    text = json.dumps(report, indent=2, sort_keys=True)
    written = []
    for path_text, body, label in ((args.out, text, "null-floor-json"),
                                   (args.markdown_out, render_markdown(report), "null-floor-markdown")):
        if path_text:
            path = Path(path_text)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
            written.append((path, label))
    if args.store_root:
        store = FileBackedHarnessStore(Path(args.store_root))
        store.put_receipt(kind="null_floor", body=report, run_id=args.run_id,
                          verdict=report["verdict"])
        for path, label in written:
            store.copy_artifact(path, run_id=args.run_id, label=label)
    print(render_markdown(report))
    return 1 if (args.fail_on_breach and report["verdict"] == BREACHED) else 0


if __name__ == "__main__":
    raise SystemExit(main())
