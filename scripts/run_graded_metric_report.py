"""Roll a run's scorecard up into the per-role numbers a chart can carry.

The scorecard holds every graded measurement one attempt at a time. This reads
it and answers two questions per provider role: what the attempts cost and how
long they took, and what each graded oracle actually measured. It calls no
provider and spends nothing.

Point it at more than one scorecard to compare runs. Rows are pooled, so the
roles and checkers are whatever those runs have in common.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.graded_metric_report import (  # noqa: E402
    build_report,
    load_scorecard,
    render_markdown,
)

ROOT = Path(__file__).resolve().parent.parent


def write_text(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return str(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scorecard", action="append", default=[],
                        help="a scorecard to read; repeat to pool several runs")
    parser.add_argument("--out", default="", help="write the JSON record here")
    parser.add_argument("--markdown-out", default="", help="write the tables here")
    parser.add_argument("--quiet", action="store_true", help="write files without printing")
    parser.add_argument("--min-scored", type=int, default=0,
                        help="exit non-zero when fewer attempts than this were scored")
    parser.add_argument("--require-cost-coverage", action="store_true",
                        help="exit non-zero unless every launched attempt reports a cost")
    return parser


def _cost_gap(record: dict) -> list[str]:
    """Roles whose provider stated a cost for some attempts but not all.

    A role that reports no cost at all is a known missing measurement and says
    so in its null reason. A role that reports a cost for part of its attempts
    is the dangerous case, because summing those gives a total that looks whole.
    """
    return [row["provider_role"] for row in record["roles"]
            if row["launched"] and row["cost_reported_attempts"] != row["launched"]]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.scorecard:
        print("no scorecard given: pass --scorecard at least once", file=sys.stderr)
        return 2

    rows: list[dict] = []
    for path in args.scorecard:
        rows.extend(load_scorecard(path))
    record = build_report(rows)
    record["scorecard_paths"] = [str(Path(path)) for path in args.scorecard]

    table = render_markdown(record)
    write_text(args.out, json.dumps(record, indent=2, sort_keys=True) + "\n")
    write_text(args.markdown_out, table)
    if not args.quiet:
        print(table)

    scored = record["counts"]["scored"]
    if scored < args.min_scored:
        print(f"scored {scored} attempts, floor is {args.min_scored}", file=sys.stderr)
        return 1
    if args.require_cost_coverage:
        gaps = _cost_gap(record)
        if gaps:
            print(f"partial cost coverage: {', '.join(gaps)}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
