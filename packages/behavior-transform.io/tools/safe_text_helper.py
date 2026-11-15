#!/usr/bin/env python3
"""Neutral local text helper.

This entry point carries forward the shared text-rule utility used by the
workspace IO helpers. It does not run legacy advanced modulation code.
"""
from __future__ import annotations

import argparse
import json
import sys

from text_rules import apply_text_rules, collect_text_rules


def _read_stdin() -> str:
    buffer = getattr(sys.stdin, "buffer", None)
    if buffer is not None:
        return buffer.read().decode("utf-8", errors="replace")
    return sys.stdin.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local text helper.")
    parser.add_argument("--json", action="store_true", help="Emit a compact JSON status.")
    parser.add_argument("--diff-only", action="store_true", help="Emit counters only.")
    args = parser.parse_args(argv)

    source_text = _read_stdin()
    rules = collect_text_rules()
    output_text, counter = apply_text_rules(source_text, rules)
    counts = {tier: int(count) for tier, count in counter.items()}
    total = sum(counts.values())

    if args.json or args.diff_only:
        sys.stdout.write(
            json.dumps(
                {
                    "status": "ok",
                    "audit_counts": counts,
                    "total": total,
                    "changed": output_text != source_text,
                }
            )
            + "\n"
        )
        return 0

    sys.stdout.write(output_text)
    if output_text and not output_text.endswith("\n"):
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
