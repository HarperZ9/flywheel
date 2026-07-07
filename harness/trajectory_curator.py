"""trajectory_curator.py — admit forum-exported trajectories as gradable data.

The trajectory analogue of task_curator.screen. A curated coding task must clear
six gates before it enters the registry; a trajectory clears the same six, adapted
to a run that cannot be cheaply re-executed like pytest:

  1. witness_matches   — recheck_witness == MATCH (the reference_passes analogue:
                         the datum re-derives independently, no forum trust).
  2. oracle_can_fail   — flipping a recorded grade input makes the re-check DRIFT.
                         A grade with no inputs, or one whose flip changes nothing,
                         verifies nothing and is REJECTED (the load-bearing gate).
  3. grade_independent — the graders are disjoint from the producers AND the answer
                         is not verbatim in the prompt (the no_solution_leak
                         analogue: a self-graded or leaked datum is REJECTED).
  4. min_coverage      — grade.checks >= MIN_CHECKS and label != UNVERIFIABLE
                         (the edge_coverage analogue).
  5. dedup             — task_id new AND sha256(norm(prompt)+norm(answer)) new.
  6. deterministic     — re-checking twice yields the identical root and reward.

curate_trajectories reports the honest recirculation ceiling: with reuse fraction
r = dup_rejections / total, the amortization ceiling is 1/(1-r). Dedup here is
request+answer identity, not full behavioral equivalence (a trajectory cannot be
re-run cheaply), so it UNDER-counts novel coverage — the safe direction for an
honest yield, never over-counting. This gate touches datum admission ONLY; it does
not feed or model backflow.py's capability-level FrontierValve.
"""
from __future__ import annotations

import copy
import hashlib
from typing import Any

from .trajectory_intake import recheck_witness

MIN_CHECKS = 2


def _norm(text: str) -> str:
    return " ".join((text or "").split()).lower()


def _content_key(row: dict[str, Any]) -> str:
    answer = row.get("trajectory", {}).get("answer") or ""
    return hashlib.sha256((_norm(row.get("prompt", "")) + "\x1f" + _norm(answer)).encode()).hexdigest()


def _can_fail(row: dict[str, Any]) -> bool:
    """A grade CAN fail iff flipping a recorded grade input makes the re-check
    DRIFT. No inputs, or a flip that changes nothing, means it verifies nothing."""
    inputs = row.get("oracle", {}).get("grade_inputs", [])
    if not inputs:
        return False
    probe = copy.deepcopy(row)
    g0 = probe["oracle"]["grade_inputs"][0]
    g0["ok"] = not bool(g0.get("ok"))
    return recheck_witness(probe)["witness"] == "DRIFT"


def _is_independent(row: dict[str, Any]) -> bool:
    grade = row.get("grade", {})
    graders = set(grade.get("graders", []))
    producers = set(grade.get("producers", []))
    if graders & producers:
        return False  # a producer graded itself
    answer = row.get("trajectory", {}).get("answer")
    if answer and _norm(answer) and _norm(answer) in _norm(row.get("prompt", "")):
        return False  # the answer leaked into the prompt
    return True


def screen_trajectory(row: dict[str, Any], existing: set[str] | None = None,
                      *, min_checks: int = MIN_CHECKS) -> dict[str, Any]:
    """Screen one exported row against the six gates. `existing` is the set of
    already-admitted keys (task_id and content keys). Returns the gate verdicts
    and whether the row is admitted (all gates PASS)."""
    existing = existing or set()
    gates: dict[str, str] = {}

    v1 = recheck_witness(row)
    gates["witness_matches"] = ("PASS" if v1["witness"] == "MATCH"
                                else f"FAIL: witness {v1['witness']} ({'; '.join(v1['reasons'])})")

    gates["oracle_can_fail"] = ("PASS" if _can_fail(row)
                                else "FAIL: grade cannot fail (no flippable input) — verifies nothing")

    gates["grade_independent"] = ("PASS" if _is_independent(row)
                                  else "FAIL: self-graded or answer leaked into prompt")

    grade = row.get("grade", {})
    checks = grade.get("checks", 0)
    label = grade.get("label")
    gates["min_coverage"] = ("PASS" if checks >= min_checks and label != "UNVERIFIABLE"
                             else f"FAIL: {checks} checks / label={label} (need >={min_checks}, not UNVERIFIABLE)")

    tid = row.get("task_id")
    ckey = _content_key(row)
    is_dup = tid in existing or ckey in existing
    gates["dedup"] = "FAIL: duplicate (task_id or prompt+answer already admitted)" if is_dup else "PASS"

    v2 = recheck_witness(row)
    deterministic = (v1["root_reproduced"] == v2["root_reproduced"]
                     and v1["reward_reproduced"] == v2["reward_reproduced"])
    gates["deterministic"] = "PASS" if deterministic else "FAIL: re-check is not reproducible"

    admitted = all(g == "PASS" for g in gates.values())
    return {"task_id": tid, "content_key": ckey, "admitted": admitted, "gates": gates}


def curate_trajectories(rows: list[dict[str, Any]],
                        existing: set[str] | None = None) -> dict[str, Any]:
    """Screen a batch. Reports admitted/rejected and the honest recirculation
    ceiling 1/(1-r) where r is the fraction rejected purely as duplicates."""
    seen: set[str] = set(existing or set())
    admitted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    dup_rejections = 0
    for row in rows:
        r = screen_trajectory(row, seen)
        if r["admitted"]:
            admitted.append(r)
            seen.add(r["task_id"])
            seen.add(r["content_key"])
        else:
            rejected.append(r)
            if r["gates"]["dedup"].startswith("FAIL"):
                dup_rejections += 1
    total = len(rows)
    reuse = round(dup_rejections / total, 4) if total else 0.0
    ceiling = round(1 / (1 - reuse), 3) if reuse < 1 else float("inf")
    return {
        "schema": "trajectory-curator.batch/1",
        "submitted": total,
        "admitted": len(admitted),
        "rejected": len(rejected),
        "admit_rate": round(len(admitted) / total, 4) if total else 0.0,
        "reuse_fraction": reuse,
        "amortization_ceiling": ceiling,
        "ceiling_note": ("1/(1-r), r = dup rejections / submitted. Recirculation "
                         "amortizes; it never compounds on novel coverage. Dedup is "
                         "prompt+answer identity, so this under-counts novelty."),
        "admitted_rows": admitted,
        "rejected_rows": rejected,
    }
