"""Report how much of a task set can run and how much of it can be scored.

Run this before a head-to-head. It calls no provider and spends nothing, so a
task set that cannot produce a readable result is caught for free rather than
after the bill.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.task_set_executability import (  # noqa: E402
    evaluate_task_set,
    render_markdown,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TASK_SET = str(ROOT / "benchmarks" / "agentic-task-set-v1.json")


def write_text(path_text: str, text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return str(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-set", default=DEFAULT_TASK_SET)
    parser.add_argument("--root", default=str(ROOT),
                        help="repository the declared inputs are resolved against")
    parser.add_argument("--out", default="", help="write the JSON record here")
    parser.add_argument("--markdown-out", default="", help="write the table here")
    parser.add_argument("--require-measurable", action="store_true",
                        help="exit non-zero unless every declared task is measured")
    parser.add_argument("--min-measured", type=int, default=0,
                        help="exit non-zero when fewer tasks than this are measured")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    record = evaluate_task_set(Path(args.root), Path(args.task_set))
    table = render_markdown(record)
    write_text(args.out, json.dumps(record, indent=2, sort_keys=True) + "\n")
    write_text(args.markdown_out, table)
    print(table)

    counts = record["counts"]
    if args.require_measurable and record["verdict"] != "TASK_SET_MEASURABLE":
        print(f"not measurable: {counts['measured']} of {counts['declared']} tasks", file=sys.stderr)
        return 1
    if counts["measured"] < args.min_measured:
        print(f"measured {counts['measured']} tasks, floor is {args.min_measured}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
