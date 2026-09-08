"""What each offline suite contributes to the record, and what did not run.

The runner beside this file measures, seals, and prints. This module holds the
shape of each result: which numbers are the headline, which caveats travel with
them, and which figures a suite declares unsealed because they belong to the
machine that ran it.

Adding a suite means writing one function here and one row in SUITES. The
runner needs no edit, so the code that decides what a number means stays clear
of the code that hashes it.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Arms that need something this script does not have. Each says what is
# missing, so an absent number reads as unmeasured rather than as zero.
NOT_RUN = [
    {"suite": "m7 capability arms",
     "needs": "a live local or frontier endpoint",
     "where": "handoff/site-designer/BENCHMARKS.md, docs/claims/2026-07-13-uplift",
     "standing_result": "retired on 2026-07-26. The arms were not independent: "
                        "the treatment's first attempt is the same call as the "
                        "baseline's only attempt, so the treatment cannot "
                        "score lower and the difference is not a comparison. "
                        "The quantity measured is verified pass@k. The retired "
                        "table read verified inference 9/10 against "
                        "single-shot 8/10, difference +0.100 with 95% CI "
                        "[-0.236, +0.420], an interval that includes zero, and "
                        "no capability uplift is claimed."},
    {"suite": "uplift_bench legacy retry diagnostic",
     "needs": "a provider list and an oracle",
     "where": "harness/uplift_bench.py, GET /api/uplift",
     "standing_result": "Formerly labeled 'uplift_bench paired arms'. "
                        "Different generation budgets and selector-as-scorer "
                        "prevent an uplift claim. See docs/UPLIFT-EVALUATION.md "
                        "for the existing matched-pool apparatus and its limits."},
    {"suite": "verified_bench private task set",
     "needs": "endpoints and a private task set the operator supplies",
     "where": "harness/verified_bench.py, POST /api/bench/run",
     "standing_result": None},
    {"suite": "classifier friction backend modes",
     "needs": "a chat backend per mode",
     "where": "harness/classifier_friction_bench.py",
     "standing_result": None},
    {"suite": "backend variants of the governed, recovery, stateful and "
              "source-mined suites",
     "needs": "a chat backend; the deterministic variants below ran instead",
     "where": "run_backend_* in the same modules",
     "standing_result": None},
]


def _accountability() -> dict[str, Any]:
    from harness.accountability_bench import score_harness, score_strawman
    harness, strawman = score_harness(), score_strawman()
    return {
        "schema": harness["benchmark"],
        "headline": {
            "harness_overall": harness["overall"],
            "strawman_overall": strawman["overall"],
            "dimensions": harness["n_dimensions"],
            "separation": round(harness["overall"] - strawman["overall"], 4),
        },
        # The strawman is the falsifier. If it scored well the benchmark
        # would be measuring nothing, so its score is reported next to the
        # harness score and never on its own.
        "credible": bool(strawman.get("credibility")),
        "non_goal": harness["non_goal"],
        # Both sides of every dimension, so the chart can show the gap rather
        # than a row of full bars that proves nothing on its own. The strawman
        # scores a name -> score map and does not cover every dimension the
        # harness does; a dimension it never scored is None, not zero.
        "detail": [{"name": d["name"], "score": d["score"],
                    "strawman": strawman["dimensions"].get(d["name"])}
                   for d in harness["dimensions"]],
    }


def _governed_agent() -> dict[str, Any]:
    from harness.governed_agent_bench import run_governed_agent_benchmark
    report = run_governed_agent_benchmark()
    m = report["metrics"]
    return {
        "schema": report["schema"],
        "headline": {"scenarios": report["scenario_count"],
                     "pass_rate": m["pass_rate"],
                     "passed": m["passed_cases"],
                     "failed": m["failed_cases"],
                     "mean_quality_score": m["mean_quality_score"]},
        "detail": [{"name": k, "score": v} for k, v in sorted(m.items())
                   if isinstance(v, (int, float)) and not isinstance(v, bool)],
    }


def _agent_recovery() -> dict[str, Any]:
    from harness.agent_recovery_bench import run_agent_recovery_benchmark
    report = run_agent_recovery_benchmark()
    m = report["metrics"]
    return {
        "schema": report["schema"],
        "headline": {"scenarios": report["scenario_count"],
                     "recovery_success_rate": m["recovery_success_rate"],
                     "silent_failure_rate": m["silent_failure_rate"],
                     "receipt_completeness": m["receipt_completeness"]},
        "detail": [{"name": k, "score": v} for k, v in sorted(m.items())
                   if isinstance(v, (int, float)) and not isinstance(v, bool)],
    }


def _stateful() -> dict[str, Any]:
    from harness.unisonai_stateful_bench import run_unisonai_stateful_benchmark
    with tempfile.TemporaryDirectory() as tmp:
        report = run_unisonai_stateful_benchmark(Path(tmp))
    # `checks` is a name -> bool map and `metrics` is the scored form of the
    # same names; the map is the count and the metrics carry the detail.
    checks = report.get("checks", {})
    return {
        "schema": report["schema"],
        "headline": {"checks": len(checks),
                     "pass_rate": report["pass_rate"],
                     "passed": bool(report["passed"])},
        "detail": [{"name": m["metric"], "score": m["value"]}
                   for m in report.get("metrics", [])
                   if isinstance(m.get("value"), (int, float))],
    }


def _source_mined() -> dict[str, Any]:
    from scripts import model_card_benchmark_shapes as shapes
    from harness.source_mined_bench import run_source_mined_benchmark
    datasets = shapes.load_datasets(
        shapes.DEFAULT_MODEL_DATASET, shapes.DEFAULT_SOCIAL_DATASET,
        shapes.DEFAULT_RESEARCH_DATASET, shapes.DEFAULT_PUBLIC_THINKER_DATASET)
    report = run_source_mined_benchmark(shapes.benchmark_cases(datasets))
    return {
        "schema": report["schema"],
        "headline": {"cases": report["case_count"],
                     "pass_rate": report["pass_rate"],
                     "passed": report["passed_cases"],
                     "failed": report["failed_cases"],
                     "metrics_asserted": report["metric_count"]},
        "detail": [],
    }


def _paired() -> dict[str, Any]:
    """The negative result, recomputed from committed per-task outcomes."""
    from harness.paired_replication import run_paired_replication
    report = run_paired_replication()
    return {
        "schema": report["schema"],
        "headline": {"delta_points": report["delta_points"],
                     "tasks": report["n_tasks"],
                     "regressions": report["paired"]["regressions"],
                     "gains": report["paired"]["gains"],
                     "p_exact": report["mcnemar"]["p_exact"]},
        # The caveats ride with the number into the record, so a surface that
        # prints the number without them is visibly missing a field rather
        # than quietly cleaner than the truth.
        "caveats": report["caveats"],
        "non_goal": report["reading"],
        "detail": [],
    }


def _receipting_cost() -> dict[str, Any]:
    """The cost side of the argument, measured on the path that ships."""
    from harness.receipting_cost_bench import run_receipting_cost_benchmark
    report = run_receipting_cost_benchmark()
    attribution, disk = report["attribution"], report["disk"]
    return {
        "schema": report["schema"],
        "headline": {
            "ms_per_witnessed_action": round(attribution["total_us"] / 1000, 2),
            "durability_share": attribution["durability_share"],
            "recheck_us_per_record": disk["verify_us_per_record"],
            "log_bytes_per_action": disk["bytes_per_action"],
            "verdict": disk["verdict"]},
        # The timings belong to the disk they were taken on. Naming them here
        # keeps them out of the seal, so the gate goes on meaning something,
        # and keeps the omission visible rather than quiet.
        "unsealed": ["ms_per_witnessed_action", "durability_share",
                     "recheck_us_per_record", "detail", "non_goal"],
        "non_goal": report["reading"],
        "caveats": report["does_not_prove"],
        "detail": [{"name": arm, "score": spread["median_us"]}
                   for arm, spread in report["arms"].items()],
    }


SUITES: list[tuple[str, str, Callable[[], dict[str, Any]]]] = [
    ("accountability", "does an unaccountable system score badly here",
     _accountability),
    ("governed-agent", "does a workflow refuse an action above its tier",
     _governed_agent),
    ("agent-recovery", "does an injected fault recover without failing quietly",
     _agent_recovery),
    ("stateful-provider-swap", "does state survive a provider swap",
     _stateful),
    ("source-mined", "do the mined checks still hold against their datasets",
     _source_mined),
    ("paired-replication",
     "did continued pretraining change general code completion",
     _paired),
    ("receipting-cost", "what does it cost to keep the receipt",
     _receipting_cost),
]
