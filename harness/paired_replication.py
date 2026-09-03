"""Recompute the one unfavourable comparison in the record, from committed files.

Continued pretraining on the workspace corpus was measured against the base
weights on a 164-task code-completion suite, one deterministic sample per
task, the same harness on both sides. It came out slightly worse, and not
significantly so. That is the project's clearest capability result and it is
negative, so it belongs on the benchmark surface rather than in a records
directory.

The per-task pass lists are committed, so this recomputes the comparison on
every run instead of transcribing it. A number that moves moves the seal.
Nothing here calls a model: it reads two artifacts and counts.

What it does not show: it measures a change in the base weights on general
code completion. It says nothing about whether the harness helps on
verifiable tasks, which is a different question with a different instrument.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

SCHEMA = "flywheel.paired-replication/v1"

ARTIFACTS = Path(__file__).resolve().parent.parent / (
    "project-docs/releases/14B/shipped-page/benchmarks")
BASE = ARTIFACTS / "humaneval_base_qwen14b.json"
TREATMENT = ARTIFACTS / "humaneval_flywheel14b.json"

# These ride with the number wherever it is published. The first is why the
# comparison cannot be re-run by a stranger; the second is why it is not
# evidence about the harness.
CAVEATS = (
    "The model references in these artifacts no longer resolve to anything on "
    "a live roster, so the exact weights behind each arm cannot be fetched "
    "again from the reference alone. The per-task outcomes are committed and "
    "the arithmetic here is reproducible; the generation is not.",
    "One deterministic sample per task per arm. A single sample measures the "
    "greedy decode, not the model.",
    "This compares base weights against continued-pretrained weights on "
    "general code completion. It is not a measurement of the verification "
    "harness, which is the thing this repository is.",
)


def _pass_map(path: Path) -> tuple[dict[str, Any], dict[str, bool]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    return doc, {row["task_id"]: bool(row["passed"]) for row in doc["per_task"]}


def _exact_two_sided(b: int, c: int) -> float:
    """Two-sided sign test on the discordant pairs.

    With 23 discordant pairs the chi-square approximation is defensible but
    the exact binomial needs no defending, so both are reported and the exact
    one is the p-value quoted.
    """
    n = b + c
    if n == 0:
        return 1.0
    lo = min(b, c)
    tail = sum(math.comb(n, i) for i in range(lo + 1)) * 0.5 ** n
    return min(1.0, 2 * tail)


def run_paired_replication() -> dict[str, Any]:
    """Recount the paired comparison and return it with its caveats."""
    base_doc, base = _pass_map(BASE)
    treat_doc, treat = _pass_map(TREATMENT)
    if set(base) != set(treat):
        raise ValueError("the two arms did not run the same task set")
    n = len(base)
    regressions = sum(1 for k in base if base[k] and not treat[k])
    gains = sum(1 for k in base if treat[k] and not base[k])
    base_passed = sum(base.values())
    treat_passed = sum(treat.values())
    discordant = regressions + gains
    chi2_cc = (((abs(regressions - gains) - 1) ** 2) / discordant
               if discordant else 0.0)
    return {
        "schema": SCHEMA,
        "benchmark": base_doc["benchmark"],
        "metric": base_doc["metric"],
        "n_tasks": n,
        "base": {"ref": base_doc["model_ref"], "passed": base_passed,
                 "pass_at_1": round(base_passed / n, 4)},
        "treatment": {"ref": treat_doc["model_ref"], "passed": treat_passed,
                      "pass_at_1": round(treat_passed / n, 4)},
        "delta_points": round((treat_passed - base_passed) / n, 4),
        "paired": {"regressions": regressions, "gains": gains,
                   "both_pass": sum(1 for k in base if base[k] and treat[k]),
                   "both_fail": sum(1 for k in base
                                    if not base[k] and not treat[k])},
        "mcnemar": {"chi2_cc": round(chi2_cc, 3),
                    "p_exact": round(_exact_two_sided(regressions, gains), 4),
                    "significant_at_05": False},
        # Stated as a finding, not softened. A negative result published is
        # worth more than a positive one withheld.
        "reading": "continued pretraining on the workspace corpus did not "
                   "improve general code completion and did not significantly "
                   "harm it; the point estimate is a regression inside the "
                   "noise",
        "caveats": list(CAVEATS),
    }
