"""Run executable source-mined benchmark checks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.source_mined_bench import run_source_mined_benchmark
from scripts.model_card_benchmark_shapes import (
    DEFAULT_ADVERSARIAL_DATASET,
    DEFAULT_UNISONAI_DATASET,
    DEFAULT_MODEL_DATASET,
    DEFAULT_AGENT_FRAMEWORK_DATASET,
    DEFAULT_ALIGNMENT_DATASET,
    DEFAULT_BUILDLANG_DATASET,
    DEFAULT_PUBLIC_THINKER_DATASET,
    DEFAULT_RESEARCH_DATASET,
    DEFAULT_SOCIAL_DATASET,
    benchmark_cases,
    load_datasets,
)


def _split_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _filter_cases(
    cases: list[dict],
    *,
    case_ids: list[str],
    categories: list[str],
) -> list[dict]:
    selected = cases
    if case_ids:
        wanted = set(case_ids)
        selected = [case for case in selected if str(case.get("id")) in wanted]
    if categories:
        wanted = set(categories)
        selected = [case for case in selected if str(case.get("category")) in wanted]
    return selected


def render_markdown(report: dict) -> str:
    lines = [
        "# Source-mined Executable Benchmark",
        "",
        f"- cases: {report['case_count']}",
        f"- passed_cases: {report['passed_cases']}",
        f"- failed_cases: {report['failed_cases']}",
        f"- pass_rate: {report['pass_rate']}",
        f"- metric_count: {report['metric_count']}",
        f"- categories: {', '.join(report['categories'])}",
        "",
        "## Case Results",
        "",
    ]
    for result in report["results"]:
        lines.extend([
            f"### `{result['case_id']}`",
            "",
            f"- category: `{result['category']}`",
            f"- passed: `{result['passed']}`",
            f"- notes: {result.get('notes', '')}",
            "",
        ])
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
    parser.add_argument("--model-dataset", type=Path, default=DEFAULT_MODEL_DATASET)
    parser.add_argument("--social-dataset", type=Path, default=DEFAULT_SOCIAL_DATASET)
    parser.add_argument("--research-dataset", type=Path, default=DEFAULT_RESEARCH_DATASET)
    parser.add_argument("--public-thinker-dataset", type=Path, default=DEFAULT_PUBLIC_THINKER_DATASET)
    parser.add_argument("--alignment-dataset", type=Path, default=DEFAULT_ALIGNMENT_DATASET)
    parser.add_argument("--agent-framework-dataset", type=Path, default=DEFAULT_AGENT_FRAMEWORK_DATASET)
    parser.add_argument("--buildlang-dataset", type=Path, default=DEFAULT_BUILDLANG_DATASET)
    parser.add_argument("--adversarial-dataset", type=Path, default=DEFAULT_ADVERSARIAL_DATASET)
    parser.add_argument("--unisonai-dataset", type=Path, default=DEFAULT_UNISONAI_DATASET)
    parser.add_argument("--case-id", default="", help="comma-separated benchmark case ids")
    parser.add_argument("--category", default="", help="comma-separated benchmark categories")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--format", choices=("json", "markdown", "validate"), default="json")
    args = parser.parse_args(argv)

    datasets = load_datasets(
        args.model_dataset,
        args.social_dataset,
        args.research_dataset,
        args.public_thinker_dataset,
        args.alignment_dataset,
        args.agent_framework_dataset,
        args.buildlang_dataset,
        args.adversarial_dataset,
        args.unisonai_dataset,
    )
    cases = _filter_cases(
        benchmark_cases(datasets),
        case_ids=_split_csv(args.case_id),
        categories=_split_csv(args.category),
    )
    if not cases:
        sys.stderr.write("no benchmark cases matched --case-id/--category filters\n")
        return 2
    report = run_source_mined_benchmark(cases)

    if args.format == "validate":
        summary = {
            "schema": report["schema"],
            "case_count": report["case_count"],
            "passed_cases": report["passed_cases"],
            "failed_cases": report["failed_cases"],
            "pass_rate": report["pass_rate"],
            "metric_count": report["metric_count"],
            "categories": report["categories"],
        }
        write_output(json.dumps(summary, indent=2) + "\n", args.output)
        return 0 if report["failed_cases"] == 0 else 1

    if args.format == "markdown":
        write_output(render_markdown(report), args.output)
        return 0 if report["failed_cases"] == 0 else 1

    write_output(json.dumps(report, indent=2) + "\n", args.output)
    return 0 if report["failed_cases"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
