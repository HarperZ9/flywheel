"""Re-run every benchmark that needs no model endpoint and no network.

Five suites qualify. They measure what the harness itself does with a
recorded situation: whether an unaccountable system scores badly on the
accountability axes, whether a governed workflow refuses an action above its
tier, whether an injected fault recovers without a silent failure, whether
state survives a provider swap, and whether the source-mined checks still
hold against their datasets. All of it is deterministic and offline, so a
reader with the repo can re-run this command and get the same numbers.

What this does NOT measure is capability. The arms that answer "does the
loop make a model solve more tasks" need a live endpoint, and running this
script does not run them. They are listed in `not_run` with the reason, so a
reader never has to guess whether a missing number was measured and hidden
or simply not measured. The July capability result stands where it was
recorded, uplift unclaimed, interval including zero.

    python scripts/run_offline_benchmarks.py

Writes docs/benchmarks/report.json and prints the headline table. The
committed copy of that file is the published record, and a test re-runs this
and compares, so the page and the numbers cannot drift apart.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SCHEMA = "flywheel.offline-benchmarks/v1"

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
    {"suite": "uplift_bench paired arms",
     "needs": "a provider list and an oracle",
     "where": "harness/uplift_bench.py, POST /api/uplift",
     "standing_result": None},
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
]


def _parity() -> dict[str, Any]:
    from harness.parity import parity_matrix
    doc = parity_matrix()
    s = doc["summary"]
    return {"declared_on": doc["declared_on"], "rows": len(doc["rows"]),
            "witnessed": s["witnessed"], "absent": s["absent"],
            "uniquely_witnessed": len(s["uniquely_witnessed"]),
            "gaps": list(s["gaps"])}


def run_all() -> dict[str, Any]:
    suites = []
    for name, question, fn in SUITES:
        started = time.perf_counter()
        result = fn()
        suites.append({"name": name, "question": question,
                       "seconds": round(time.perf_counter() - started, 3),
                       **result})
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "python": platform.python_version(),
        "suites": suites,
        "not_run": NOT_RUN,
        "parity": _parity(),
    }
    # The hash covers the results and skips the timings, so two runs of the
    # same code agree and a changed number cannot ride in unnoticed.
    sealed = {"suites": [{k: v for k, v in s.items() if k != "seconds"}
                         for s in suites],
              "parity": report["parity"]}
    report["result_sha256"] = hashlib.sha256(
        json.dumps(sealed, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return report


def render_table(report: dict[str, Any]) -> str:
    lines = [f"offline benchmarks  python {report['python']}  "
             f"seal {report['result_sha256'][:16]}"]
    for suite in report["suites"]:
        head = "  ".join(f"{k}={v}" for k, v in suite["headline"].items())
        lines.append(f"  {suite['name']:<24} {head}")
    p = report["parity"]
    lines.append(f"  {'parity':<24} rows={p['rows']}  witnessed={p['witnessed']}"
                 f"  absent={p['absent']}  gaps={len(p['gaps'])}")
    lines.append(f"  not run: {len(report['not_run'])} suites need a live "
                 "endpoint, each named in the report")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="docs/benchmarks",
                    help="directory to write report.json into")
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args(argv)
    report = run_all()
    print(render_table(report))
    if not args.no_write:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "report.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
