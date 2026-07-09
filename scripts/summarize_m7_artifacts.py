#!/usr/bin/env python3
"""Summarize M7 scorecard artifacts into a compact Markdown table."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_ARMS = (
    "single_shot",
    "no_search",
    "flat_n",
    "verified_inference",
    "local_ollama",
    "frontier_single_shot",
    "frontier_codex-plan",
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _pass_rate(scorecard: dict[str, Any], arm: str) -> str:
    data = scorecard.get("arms", {}).get(arm, {})
    if not isinstance(data, dict) or "pass_rate" not in data:
        return ""
    try:
        return f"{float(data['pass_rate']):.3f}"
    except (TypeError, ValueError):
        return str(data["pass_rate"])


def summarize(paths: list[Path], arms: tuple[str, ...] = DEFAULT_ARMS) -> str:
    header = ["artifact", "model_ref", "tasks", *arms]
    rows = ["| " + " | ".join(header) + " |",
            "| " + " | ".join("---" for _ in header) + " |"]
    for path in sorted(paths):
        try:
            scorecard = _load(path)
        except Exception as exc:
            rows.append(f"| `{path}` | ERROR: {exc} |  | " + " | ".join("" for _ in arms) + " |")
            continue
        meta = scorecard.get("meta", {}) if isinstance(scorecard.get("meta"), dict) else {}
        row = [
            f"`{path}`",
            str(meta.get("model_ref", "")),
            str(meta.get("n_tasks", "")),
            *(_pass_rate(scorecard, arm) for arm in arms),
        ]
        rows.append("| " + " | ".join(row) + " |")
    return "\n".join(rows) + "\n"


def _expand(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        matched = sorted(Path().glob(pattern)) if not Path(pattern).is_absolute() else sorted(Path(pattern).parent.glob(Path(pattern).name))
        paths.extend(p for p in matched if p.is_file())
    return sorted(set(paths))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("patterns", nargs="*", default=["artifacts*.json", "C:/tmp/m7_*.json"])
    parser.add_argument("--output", "-o", default="", help="optional Markdown output path")
    args = parser.parse_args(argv)

    body = summarize(_expand(args.patterns))
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(body, encoding="utf-8")
    else:
        print(body, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
