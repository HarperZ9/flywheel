"""paired_comparison.py -- cluster-aware paired comparison over bench attempts.

A task is a cluster. Repetitions of the same task share that task's difficulty,
so (task, rep) pairs are not independent units, and an exact McNemar over them
would borrow significance from correlation. The retired pilot arithmetic made
exactly this mistake: 12 (task, rep) pairs presented as 12 independent pairs
when the independent unit count was 4 task clusters.

This module is the guard. It aggregates paired attempts to task level, emits
per-task discordance descriptives always, and emits a pooled exact McNemar p
(``findings_stats.mcnemar``) with its MDE (``statistics.mcnemar_mde``) ONLY
when the units are genuine task-level pairs (one rep per task, both arms) and
there are at least ``MIN_TASK_CLUSTERS`` tasks. Anything less is a structured
refusal naming the reason, never a smaller p.

Stdlib plus the two sibling statistics modules. Deterministic.
"""
from __future__ import annotations

from .findings_stats import mcnemar
from .statistics import mcnemar_mde

SCHEMA = "flywheel.paired-comparison/v1"

BUDGET_SCHEMA = "flywheel.inner-call-budget/v1"

MIN_TASK_CLUSTERS = 5

_DOES_NOT_PROVE = [
    "NOT_PROVES_HARNESS_SUPERIORITY: a paired delta over one task set speaks "
    "only about that task set; task authorship and selection carry into it.",
    "NOT_PROVES_INDEPENDENCE_WITHIN_TASKS: per-task rows describe correlated "
    "repetitions; they are descriptives, and no per-task p accompanies them.",
]


def _attempt_index(arm: dict) -> tuple[str, dict]:
    """Validate one arm and index its attempts by (task_id, repetition)."""
    name = arm.get("arm")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("an arm needs a nonempty 'arm' name")
    attempts = arm.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise ValueError(f"arm {name!r} needs a nonempty 'attempts' list")
    index: dict = {}
    for row in attempts:
        task = row.get("task_id")
        rep = row.get("repetition")
        passed = row.get("passed")
        if not isinstance(task, str) or not task.strip():
            raise ValueError(f"arm {name!r}: attempt without a task_id")
        if type(rep) is not int or rep < 0:
            raise ValueError(
                f"arm {name!r} task {task!r}: repetition must be a "
                "nonnegative integer")
        if type(passed) is not bool:
            raise ValueError(
                f"arm {name!r} task {task!r} rep {rep}: 'passed' must be a "
                "bool; an unverifiable attempt is not a pair member")
        if (task, rep) in index:
            raise ValueError(
                f"arm {name!r}: duplicate attempt for task {task!r} rep {rep}")
        index[(task, rep)] = passed
    return name, index


def _refusal(base: dict, reason: str, detail: str, **extra) -> dict:
    out = dict(base)
    out["refused"] = {"reason": reason, "detail": detail, **extra}
    return out


def _task_rows(tasks: list, reps_by_task: dict, a_index: dict,
               b_index: dict) -> list:
    rows = []
    for task in tasks:
        reps = reps_by_task[task]
        a_only = sum(1 for r in reps
                     if a_index[(task, r)] and not b_index[(task, r)])
        b_only = sum(1 for r in reps
                     if not a_index[(task, r)] and b_index[(task, r)])
        rows.append({
            "task_id": task, "n_reps": len(reps),
            "a_passes": sum(1 for r in reps if a_index[(task, r)]),
            "b_passes": sum(1 for r in reps if b_index[(task, r)]),
            "a_only": a_only, "b_only": b_only,
            "discordant": a_only + b_only,
            "concordant": len(reps) - a_only - b_only})
    return rows


def _pool_or_refuse(out: dict, reps_by_task: dict, a_index: dict,
                    b_index: dict, alpha: float, min_clusters: int) -> dict:
    """Attach the pooled statistic, or the refusal the design demands."""
    clustered = [row["task_id"] for row in out["per_task"]
                 if row["n_reps"] > 1]
    if clustered:
        out["pooled_refused"] = {
            "reason": "cluster_correlated_reps",
            "detail": (
                f"tasks {clustered} carry more than one repetition; reps "
                "within a task share the task's difficulty, so pooling "
                "(task, rep) pairs as independent would overstate the "
                "evidence. Per-task discordance descriptives are the "
                "honest output at this design.")}
        return out
    tasks = [row["task_id"] for row in out["per_task"]]
    if len(tasks) < min_clusters:
        out["pooled_refused"] = {
            "reason": "cluster_count_below_minimum",
            "detail": (
                f"{len(tasks)} task cluster(s) is below the minimum of "
                f"{min_clusters}; a pooled p over so few clusters reads as "
                "more evidence than the design holds. Per-task rows only.")}
        return out
    verdicts = [{"a": a_index[(t, reps_by_task[t][0])],
                 "b": b_index[(t, reps_by_task[t][0])]} for t in tasks]
    stat = mcnemar(verdicts, "a", "b")
    out["pooled"] = {
        "unit": "task", **stat,
        "mde": mcnemar_mde(len(tasks), stat["discordant"], alpha=alpha)}
    return out


def paired_comparison(arm_a: dict, arm_b: dict, *, alpha: float = 0.05,
                      min_clusters: int = MIN_TASK_CLUSTERS) -> dict:
    """Task-level paired comparison of two arms, or a structured refusal.

    Each arm is ``{"arm": name, "attempts": [{"task_id", "repetition",
    "passed"}, ...]}``. Pairing is by (task_id, repetition) across arms, so
    both arms must cover the same tasks and the same repetitions per task; a
    mismatch refuses the whole comparison because the pairing is undefined,
    not merely underpowered.
    """
    name_a, a_index = _attempt_index(arm_a)
    name_b, b_index = _attempt_index(arm_b)
    base = {"schema": SCHEMA, "statistic": "cluster_paired_comparison",
            "arm_a": name_a, "arm_b": name_b}
    tasks_a = {t for t, _ in a_index}
    tasks_b = {t for t, _ in b_index}
    if tasks_a != tasks_b:
        return _refusal(
            base, "unequal_task_sets",
            "the arms cover different tasks, so task-level pairing is "
            "undefined; run both arms over one task set",
            a_only_tasks=sorted(tasks_a - tasks_b),
            b_only_tasks=sorted(tasks_b - tasks_a))
    tasks = sorted(tasks_a)
    reps_by_task = {}
    for task in tasks:
        reps_a = {r for t, r in a_index if t == task}
        reps_b = {r for t, r in b_index if t == task}
        if reps_a != reps_b:
            return _refusal(
                base, "unequal_repetition_sets",
                f"task {task!r} has repetitions {sorted(reps_a)} in "
                f"{name_a} and {sorted(reps_b)} in {name_b}; attempt-level "
                "pairing is undefined")
        reps_by_task[task] = sorted(reps_a)
    per_task = _task_rows(tasks, reps_by_task, a_index, b_index)
    out = {**base, "n_tasks": len(tasks),
           "n_attempt_pairs": sum(row["n_reps"] for row in per_task),
           "per_task": per_task, "pooled": None,
           "does_not_prove": list(_DOES_NOT_PROVE)}
    return _pool_or_refuse(out, reps_by_task, a_index, b_index,
                           alpha, min_clusters)


def _count_index(arm: dict) -> tuple[str, dict]:
    """Validate one arm and index inner_call_count by (task_id, repetition).

    A missing or None count is kept as None: pre-budget receipts exist, and
    the pair-level check refuses those pairs by name instead of guessing.
    A present count of the wrong type is caller malformation and raises.
    """
    name = arm.get("arm")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("an arm needs a nonempty 'arm' name")
    attempts = arm.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise ValueError(f"arm {name!r} needs a nonempty 'attempts' list")
    index: dict = {}
    for row in attempts:
        task = row.get("task_id")
        rep = row.get("repetition")
        count = row.get("inner_call_count")
        if not isinstance(task, str) or not task.strip():
            raise ValueError(f"arm {name!r}: attempt without a task_id")
        if type(rep) is not int or rep < 0:
            raise ValueError(
                f"arm {name!r} task {task!r}: repetition must be a "
                "nonnegative integer")
        if count is not None and (type(count) is not int or count < 0):
            raise ValueError(
                f"arm {name!r} task {task!r} rep {rep}: inner_call_count "
                "must be a nonnegative integer or absent")
        if (task, rep) in index:
            raise ValueError(
                f"arm {name!r}: duplicate attempt for task {task!r} rep {rep}")
        index[(task, rep)] = count
    return name, index


def _pair_budget_row(key: tuple, a_count, b_count, name_a: str, name_b: str,
                     budget_a: int, budget_b: int) -> dict | None:
    task, rep = key
    row = {"task_id": task, "repetition": rep,
           "a_inner_call_count": a_count, "b_inner_call_count": b_count}
    unrecorded = [name for name, count in
                  ((name_a, a_count), (name_b, b_count)) if count is None]
    if unrecorded:
        return {**row, "reason": "inner_call_count_unrecorded",
                "detail": (f"arm(s) {unrecorded} did not record "
                           "inner_call_count; a pair without a recorded "
                           "count cannot be shown on budget")}
    if a_count != budget_a or b_count != budget_b:
        return {**row, "reason": "inner_call_budget_mismatch",
                "detail": (f"{name_a} recorded {a_count} inner call(s) "
                           f"against proposer_invocations_max={budget_a}; "
                           f"{name_b} recorded {b_count} against "
                           f"proposer_invocations_max={budget_b}")}
    return None


def inner_call_budget_check(arm_a: dict, arm_b: dict, *,
                            budgets: dict) -> dict:
    """Refuse pairs whose inner-call counts differ from preregistered budgets.

    Each arm is ``{"arm": name, "attempts": [{"task_id", "repetition",
    "inner_call_count"}, ...]}`` and ``budgets`` maps each arm name to its
    preregistered inner-call budget (a positive int; the bare arm's is 1 by
    construction). A pair whose recorded counts differ from the budgets, or
    whose count is unrecorded, is refused by name; unequal task or repetition
    sets refuse the whole check because pairing is undefined.
    """
    name_a, a_index = _count_index(arm_a)
    name_b, b_index = _count_index(arm_b)
    for name in (name_a, name_b):
        budget = budgets.get(name) if isinstance(budgets, dict) else None
        if type(budget) is not int or budget < 1:
            raise ValueError(
                f"budgets must map arm {name!r} to a positive int "
                "preregistered inner-call budget")
    base = {"schema": BUDGET_SCHEMA, "statistic": "inner_call_budget_check",
            "arm_a": name_a, "arm_b": name_b,
            "budgets": {name_a: budgets[name_a], name_b: budgets[name_b]}}
    if set(a_index) != set(b_index):
        reason = ("unequal_task_sets"
                  if {t for t, _ in a_index} != {t for t, _ in b_index}
                  else "unequal_repetition_sets")
        return _refusal(
            base, reason,
            "the arms cover different (task, repetition) pairs, so "
            "pair-level budget comparison is undefined")
    refused = [row for row in (
        _pair_budget_row(key, a_index[key], b_index[key], name_a, name_b,
                         budgets[name_a], budgets[name_b])
        for key in sorted(a_index)) if row is not None]
    return {**base, "n_pairs": len(a_index),
            "admissible_pairs": len(a_index) - len(refused),
            "refused_pairs": refused}
