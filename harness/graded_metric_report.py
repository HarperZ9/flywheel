"""Turn a run's scorecard into the per-role numbers a chart can carry.

A scorecard row already holds everything the graded oracles measured. It holds
it one attempt at a time, in a 365 KB document with sixty-odd keys per row, and
nothing in the repository rolled it up. So the published benchmark surface could
show which harness passed and never show by how much, or what the answer cost.

This module reads a scorecard and answers two questions per provider role:

  efficiency  what fraction of attempts reached a provider, what fraction came
              back readable, how long they took, and what they cost
  quality     for each graded checker, the mean of every metric it reported

Both halves keep their denominators. A rate over zero attempts is reported as
null with the reason, never as zero or one. A cost is reported only for the
attempts whose provider actually stated one, and the coverage travels with it,
because four of the five roles in the 2026-09-03 run report no cost at all and
a total that hides that reads as though the run was nearly free.

Reading is all this does. It calls no provider and writes nothing.
"""
from __future__ import annotations

import json
from pathlib import Path
import statistics
from collections.abc import Iterable
from typing import Any, Callable

from harness.attempt_attribution import attribute, recovery

SCHEMA = "flywheel.graded_metric_report/v1"
SCORED_STATES = ("pass", "fail")

# Which way is better, for a chart that has to orient a bar without a caption.
DIRECTION = {
    "measurement_fidelity": "higher",
    "unsupported_claim_recall": "higher",
    "supported_claim_precision": "higher",
    "evidence_bound_score": "higher",
    "fabricated_measurements": "lower",
    "pair_recall": "higher",
    "pair_precision": "higher",
    "false_pair_count": "lower",
    "trap_pairs_reported": "lower",
    "value_ratio": "higher",
    "budget_overrun_usd": "lower",
    "wasted_spend_usd": "lower",
    "spend_usd": "neutral",
    "failure_code_count": "lower",
}

DOES_NOT_PROVE = [
    "A mean over one repetition is a reading, not an estimate. No interval is "
    "reported because none is earned at this sample size.",
    "Cost covers the attempts whose provider stated a cost. A role with no cost "
    "coverage is not cheaper, it is unmeasured.",
    "Latency is wall clock on one machine and includes local model load time.",
    "A role that never returned a readable result has no quality numbers here, "
    "which is a fact about this run and not a score of zero. Why an attempt went "
    "ungraded is reported beside it, because a malformed answer and a missing one "
    "are different failures.",
    "An envelope found inside a refused answer was still refused, and no checker "
    "graded it. That it was there says the harness produced an answer, and it does "
    "not say the answer was right.",
    "The graded metrics come from in-tree fixtures. They measure a harness "
    "against those tasks and not against a customer workload.",
]


def load_scorecard(path: str | Path) -> list[dict[str, Any]]:
    """Read the rows of one `harness.cross-harness-task-scorecard/v1` file."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = doc.get("rows")
    if not isinstance(rows, list):
        raise ValueError(f"{path}: no rows")
    return [row for row in rows if isinstance(row, dict)]


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _cost(row: dict[str, Any]) -> float | None:
    observation = (row.get("metrics") or {}).get("resource_observation") or {}
    return _number(observation.get("provider_reported_cost_usd"))


def _latency(row: dict[str, Any]) -> float | None:
    return _number((row.get("metrics") or {}).get("latency_ms"))


def _output_tokens(row: dict[str, Any]) -> float | None:
    usage = (row.get("metrics") or {}).get("usage") or {}
    return _number((usage.get("aggregate") or {}).get("output_tokens"))


def _rate(hits: int, total: int) -> float | None:
    """A rate with no denominator is not zero. It is unmeasured."""
    return round(hits / total, 4) if total else None


def _percentile(values: list[float], fraction: float) -> float | None:
    """Nearest-rank. Exact for the sample, and it never invents a value."""
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round(fraction * (len(ordered) - 1))))
    return round(ordered[index], 4)


def _scored(row: dict[str, Any]) -> bool:
    return row.get("oracle_state") in SCORED_STATES


def summarize_role(role: str, rows: list[dict[str, Any]],
                   read_text: Callable[[str], str | None] | None = None) -> dict[str, Any]:
    """Efficiency for one provider role, with every denominator kept.

    `read_text` opens the recorded output of an attempt that was refused at
    the envelope. Without it the refusals are still counted and the question
    of whether they held an answer stays null, which is what it is.
    """
    launched = [row for row in rows if row.get("launched")]
    scored = [row for row in rows if _scored(row)]
    passed = sum(1 for row in scored if row.get("oracle_state") == "pass")
    latencies = [value for value in (_latency(row) for row in launched) if value is not None]
    costed = [value for value in (_cost(row) for row in launched) if value is not None]
    tokens = [value for value in (_output_tokens(row) for row in launched) if value is not None]
    cost_total = round(sum(costed), 4) if costed else None

    nulls: dict[str, str] = {}
    if not costed:
        nulls["cost_usd_total"] = "provider_cost_unavailable"
    if not tokens:
        nulls["output_tokens_total"] = "provider_usage_unavailable"
    cost_per_scored = None
    if cost_total is None:
        nulls["cost_usd_per_scored_attempt"] = "provider_cost_unavailable"
    elif not scored:
        nulls["cost_usd_per_scored_attempt"] = "no_readable_result"
    elif len(costed) < len(launched):
        nulls["cost_usd_per_scored_attempt"] = "partial_cost_coverage"
    else:
        cost_per_scored = round(cost_total / len(scored), 4)

    return {
        "provider_role": role,
        "attempts": len(rows),
        "launched": len(launched),
        "blocked": sum(1 for row in rows if row.get("blocked")),
        "returned": sum(1 for row in rows if row.get("execution_state") == "returned"),
        "scored": len(scored),
        "oracle_pass": passed,
        "launch_rate": _rate(len(launched), len(rows)),
        "readable_rate": _rate(len(scored), len(rows)),
        "pass_rate": _rate(passed, len(scored)),
        "latency_ms_median": _percentile(latencies, 0.5),
        "latency_ms_p90": _percentile(latencies, 0.9),
        "cost_usd_total": cost_total,
        "cost_reported_attempts": len(costed),
        "cost_coverage": _rate(len(costed), len(launched)),
        "cost_usd_per_scored_attempt": cost_per_scored,
        "output_tokens_total": int(sum(tokens)) if tokens else None,
        "unreadable_reasons": attribute(rows),
        "envelope_recovery": recovery(rows, read_text) if read_text else None,
        "null_reasons": nulls,
        "models_observed": sorted({str(row.get("model_id") or "") for row in rows} - {""}),
    }


def _graded_values(row: dict[str, Any]) -> dict[str, float]:
    evidence = (row.get("oracle_evidence") or {}).get("evidence") or {}
    values = {}
    for name, value in evidence.items():
        number = _number(value)
        if number is not None:
            values[str(name)] = number
    return values


def summarize_checker(checker_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Quality for one checker: every metric it reported, per role."""
    graded = [(str(row.get("provider_role") or ""), _graded_values(row)) for row in rows]
    names: list[str] = []
    for _, values in graded:
        for name in values:
            if name not in names:
                names.append(name)
    roles = sorted({role for role, _ in graded} - {""})
    metrics = []
    for name in sorted(names):
        entries = []
        for role in roles:
            seen = [values[name] for owner, values in graded if owner == role and name in values]
            entries.append({
                "provider_role": role,
                "n": len(seen),
                "mean": round(statistics.fmean(seen), 4) if seen else None,
                "min": round(min(seen), 4) if seen else None,
                "max": round(max(seen), 4) if seen else None,
            })
        metrics.append({
            "metric": name,
            "direction": DIRECTION.get(name, "unknown"),
            "roles": entries,
        })
    return {
        "checker_id": checker_id,
        "task_ids": sorted({str(row.get("task_id") or "") for row in rows} - {""}),
        "scored_attempts": len(rows),
        "metrics": metrics,
    }


def build_report(rows: list[dict[str, Any]], read_text: Callable[[str], str | None] | None = None,
                 limitations: Iterable[str] = ()) -> dict[str, Any]:
    """One record holding both halves, plus what the run cannot support.

    `limitations` carries what the rows cannot show, such as a source tree never
    checked. They append to the standing list, so a caller cannot drop one.
    """
    roles = sorted({str(row.get("provider_role") or "") for row in rows} - {""})
    by_checker: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not _scored(row):
            continue
        checker = str((row.get("oracle_evidence") or {}).get("checker_id") or "")
        if checker:
            by_checker.setdefault(checker, []).append(row)
    return {
        "schema": SCHEMA,
        "run_ids": sorted({str(row.get("run_id") or "") for row in rows} - {""}),
        "source_commits": sorted({str(row.get("source_commit") or "") for row in rows} - {""}),
        "task_set_ids": sorted({str(row.get("task_set_id") or "") for row in rows} - {""}),
        "counts": {
            "attempts": len(rows),
            "launched": sum(1 for row in rows if row.get("launched")),
            "scored": sum(1 for row in rows if _scored(row)),
            "roles": len(roles),
            "graded_checkers": len(by_checker),
        },
        "roles": [summarize_role(role, [row for row in rows
                                        if row.get("provider_role") == role], read_text)
                  for role in roles],
        "checkers": [summarize_checker(name, by_checker[name]) for name in sorted(by_checker)],
        "does_not_prove": [*DOES_NOT_PROVE, *limitations],
    }


def _cell(value: Any) -> str:
    return "not reported" if value is None else str(value)


def _efficiency_rows(record: dict[str, Any]) -> list[str]:
    lines = []
    for row in record["roles"]:
        counted = f"{row['launched']}/{row['attempts']} | {row['scored']}/{row['attempts']}"
        rates = f"{_cell(row['launch_rate'])} | {_cell(row['readable_rate'])}"
        spend = f"{_cell(row['cost_usd_total'])} | {_cell(row['cost_coverage'])}"
        lines.append(f"| {row['provider_role']} | {counted} | {rates} "
                     f"| {_cell(row['latency_ms_median'])} | {spend} |")
    return lines


def render_markdown(record: dict[str, Any]) -> str:
    """The same record as a table, for a reader who will not open the JSON."""
    counts = record["counts"]
    lines = [
        "# Graded metric report", "",
        f"- attempts: {counts['attempts']}",
        f"- launched: {counts['launched']}",
        f"- scored: {counts['scored']}",
        f"- graded checkers reporting: {counts['graded_checkers']}", "",
        "## Efficiency by role", "",
        "| role | launched | scored | launch rate | readable rate | median ms "
        "| cost usd | cost coverage |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines += _efficiency_rows(record)
    for checker in record["checkers"]:
        lines += ["", f"## {checker['checker_id']}", "",
                  f"Scored attempts: {checker['scored_attempts']}", ""]
        if not checker["metrics"]:
            # A checker can score an attempt and report no number at all, which
            # is what the 2026-09-03 run did. Saying so is the report. An empty
            # table would read as though the metrics came back at zero.
            lines.append("This checker reported no numeric evidence on these attempts.")
            continue
        header = [entry["provider_role"] for entry in checker["metrics"][0]["roles"]]
        lines += ["| metric | better | " + " | ".join(header) + " |",
                  "| --- | --- |" + " --- |" * len(header)]
        for metric in checker["metrics"]:
            cells = " | ".join(_cell(entry["mean"]) for entry in metric["roles"])
            lines.append(f"| {metric['metric']} | {metric['direction']} | {cells} |")
    lines += ["", "## What this does not prove", ""]
    lines += ["- " + item for item in record["does_not_prove"]]
    return "\n".join(lines) + "\n"
