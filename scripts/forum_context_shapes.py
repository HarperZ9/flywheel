"""Emit benchmark-ready cases from curated forum context-shape notes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


DEFAULT_DATASET = (
    Path(__file__).resolve().parents[1]
    / "dataset"
    / "forum_context_shapes_2026-07-08.json"
)
CASE_SCHEMA = "forum.benchmark-case/v1"


class DatasetError(ValueError):
    """Raised when the forum context-shape dataset is malformed."""


def load_dataset(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    validate_dataset(data)
    return data


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DatasetError(f"{label} must be an object")
    return value


def _require_nonempty_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise DatasetError(f"{label} must be a non-empty list")
    return value


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DatasetError(f"{label} must be a non-empty string")
    return value


def validate_dataset(data: dict[str, Any]) -> None:
    _require_mapping(data, "dataset")
    if data.get("schema") != "forum-context-shapes/v1":
        raise DatasetError("dataset.schema must be forum-context-shapes/v1")

    sources = _require_nonempty_list(data.get("sources"), "dataset.sources")
    source_ids: set[str] = set()
    for index, raw_source in enumerate(sources):
        source = _require_mapping(raw_source, f"sources[{index}]")
        source_id = _require_text(source.get("id"), f"sources[{index}].id")
        if source_id in source_ids:
            raise DatasetError(f"duplicate source id: {source_id}")
        source_ids.add(source_id)
        _require_text(source.get("name"), f"sources[{index}].name")
        _require_text(source.get("url"), f"sources[{index}].url")
        _require_text(source.get("context_shape"), f"sources[{index}].context_shape")
        _require_nonempty_list(source.get("signals"), f"sources[{index}].signals")

    shapes = _require_nonempty_list(data.get("context_shapes"), "dataset.context_shapes")
    case_ids: set[str] = set()
    for index, raw_shape in enumerate(shapes):
        shape = _require_mapping(raw_shape, f"context_shapes[{index}]")
        _require_text(shape.get("id"), f"context_shapes[{index}].id")
        for source_id in _require_nonempty_list(
            shape.get("source_ids"), f"context_shapes[{index}].source_ids"
        ):
            if source_id not in source_ids:
                raise DatasetError(f"unknown source id on shape {shape['id']}: {source_id}")

        case = _require_mapping(
            shape.get("benchmark_case"), f"context_shapes[{index}].benchmark_case"
        )
        case_id = _require_text(case.get("id"), f"context_shapes[{index}].benchmark_case.id")
        if case_id in case_ids:
            raise DatasetError(f"duplicate benchmark case id: {case_id}")
        case_ids.add(case_id)
        _require_text(case.get("objective"), f"{case_id}.objective")
        _require_text(case.get("task_prompt"), f"{case_id}.task_prompt")
        _require_nonempty_list(case.get("oracle_checks"), f"{case_id}.oracle_checks")
        _require_nonempty_list(case.get("metrics"), f"{case_id}.metrics")


def benchmark_cases(data: dict[str, Any]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for shape in data["context_shapes"]:
        case = dict(shape["benchmark_case"])
        case["schema"] = CASE_SCHEMA
        case["context_shape_id"] = shape["id"]
        case["source_ids"] = list(shape["source_ids"])
        case["source_pattern"] = shape["pattern"]
        case["tool_implications"] = list(shape.get("tool_implications", []))
        cases.append(case)
    return cases


def render_markdown(data: dict[str, Any]) -> str:
    lines: list[str] = [
        "# Reddit Forum Context Shapes - 2026-07-08",
        "",
        "## Purpose",
        "",
        str(data["purpose"]),
        "",
        "## Sources",
        "",
        "| Source | Context shape | Tool relevance |",
        "|---|---|---|",
    ]

    for source in data["sources"]:
        relevance = "; ".join(source.get("tool_relevance", []))
        lines.append(
            f"| [{source['name']}]({source['url']}) | {source['context_shape']} | {relevance} |"
        )

    lines.extend(["", "## Benchmark Seeds", ""])
    for case in benchmark_cases(data):
        lines.extend(
            [
                f"### `{case['id']}`",
                "",
                f"Objective: {case['objective']}",
                "",
                f"Source shape: `{case['context_shape_id']}`",
                "",
                "Oracle checks:",
            ]
        )
        lines.extend(f"- {check}" for check in case["oracle_checks"])
        lines.append("")
        lines.append("Metrics:")
        lines.extend(f"- `{metric}`" for metric in case["metrics"])
        lines.append("")

    lines.extend(["## Tool Actions", ""])
    for action in data.get("tool_actions", []):
        lines.append(f"- `{action['id']}` -> `{action['target']}`: {action['action']}")
    lines.append("")
    return "\n".join(lines)


def write_output(text: str, output: Path | None) -> None:
    if output is None:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--format",
        choices=("benchmark-json", "markdown", "validate"),
        default="benchmark-json",
    )
    args = parser.parse_args(argv)

    try:
        data = load_dataset(args.dataset)
    except (OSError, json.JSONDecodeError, DatasetError) as exc:
        sys.stderr.write(f"forum context dataset error: {exc}\n")
        return 2

    if args.format == "markdown":
        write_output(render_markdown(data), args.output)
        return 0

    if args.format == "validate":
        summary = {
            "schema": data["schema"],
            "sources": len(data["sources"]),
            "context_shapes": len(data["context_shapes"]),
            "benchmark_cases": len(benchmark_cases(data)),
        }
        write_output(json.dumps(summary, indent=2) + "\n", args.output)
        return 0

    payload = {
        "schema": "forum.benchmark-case-set/v1",
        "generated_from": str(args.dataset),
        "cases": benchmark_cases(data),
    }
    write_output(json.dumps(payload, indent=2) + "\n", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
