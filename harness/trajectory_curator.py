"""trajectory_curator.py — admit forum-exported trajectories as gradable data.

The trajectory analogue of task_curator.screen. A curated coding task must clear
six gates before it enters the registry; a trajectory clears the same six, adapted
to a run that cannot be cheaply re-executed like pytest:

  1. witness_matches   — recheck_witness == MATCH (the reference_passes analogue:
                         the datum re-derives independently, no forum trust).
  2. oracle_can_fail   — the load-bearing gate, three clauses. (a) flipping a
                         recorded grade input makes the re-check DRIFT (the reward
                         is bound to its inputs); (b) every grade input is backed
                         by a hash-chained entry with the same actor+kind (a check
                         outside the witnessed record is fabricated); (c) every
                         grader actor carries a recorded ok=false counter-example
                         (in this row, elsewhere in the batch, or in a supplied
                         refusal witness). A grader never seen to refuse anything
                         is a rubber stamp: flip arithmetic alone proves only that
                         reward is a function of its inputs, never that the grader
                         can fail. No counter-example, no admission.
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
from collections import Counter
from typing import Any

from .trajectory_intake import recheck_witness

MIN_CHECKS = 2


def _norm(text: str) -> str:
    return " ".join((text or "").split()).lower()


def _content_key(row: dict[str, Any]) -> str:
    answer = row.get("trajectory", {}).get("answer") or ""
    return hashlib.sha256((_norm(row.get("prompt", "")) + "\x1f" + _norm(answer)).encode()).hexdigest()


def _chain_backed(row: dict[str, Any]) -> tuple[bool, str]:
    """Every grade input must be backed by a hash-chained entry with the same
    actor+kind, with multiplicity. Payload bodies are not shipped, so the ok
    bit cannot be re-read; actor+kind+count is what the sealed chain can bind.
    An input with no chained entry is a fabricated check."""
    inputs = row.get("oracle", {}).get("grade_inputs", [])
    entries = Counter((e.get("actor"), e.get("kind"))
                      for e in row.get("trajectory", {}).get("entries", []))
    needed = Counter((g.get("actor"), g.get("kind")) for g in inputs)
    for (actor, kind), n in needed.items():
        if entries[(actor, kind)] < n:
            return False, f"grade input {actor}/{kind} has no hash-chained entry backing it"
    return True, ""


def _can_fail(row: dict[str, Any],
              refusal_witness: set[str] | None = None) -> tuple[bool, str]:
    """The load-bearing gate. (a) flipping a recorded input makes the re-check
    DRIFT (reward bound to inputs); (b) every input is chain-backed; (c) every
    grader actor has a recorded ok=false counter-example, in-row or witnessed.
    Flip arithmetic alone is a tautology: it proves reward is a function of its
    inputs, never that the grader can emit ok=false on bad work."""
    inputs = row.get("oracle", {}).get("grade_inputs", [])
    if not inputs:
        return False, "no flippable input"
    probe = copy.deepcopy(row)
    g0 = probe["oracle"]["grade_inputs"][0]
    g0["ok"] = not bool(g0.get("ok"))
    if recheck_witness(probe)["witness"] != "DRIFT":
        return False, "flipping a recorded input changes nothing"
    backed, reason = _chain_backed(row)
    if not backed:
        return False, reason
    witnessed = set(refusal_witness or set())
    witnessed |= {g.get("actor") for g in inputs if g.get("ok") is False}
    for actor in {g.get("actor") for g in inputs}:
        if actor not in witnessed:
            return False, (f"grader {actor!r} has no recorded refusal "
                           f"(rubber stamp until a counter-example exists)")
    return True, ""


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
                      *, min_checks: int = MIN_CHECKS,
                      grader_refusals: set[str] | None = None) -> dict[str, Any]:
    """Screen one exported row against the six gates. `existing` is the set of
    already-admitted keys (task_id and content keys). `grader_refusals` is the
    refusal witness: grader actors with a recorded ok=false counter-example
    (from this batch or previously admitted data). Returns the gate verdicts
    and whether the row is admitted (all gates PASS)."""
    existing = existing or set()
    gates: dict[str, str] = {}

    v1 = recheck_witness(row)
    gates["witness_matches"] = ("PASS" if v1["witness"] == "MATCH"
                                else f"FAIL: witness {v1['witness']} ({'; '.join(v1['reasons'])})")

    can_fail, why = _can_fail(row, grader_refusals)
    gates["oracle_can_fail"] = ("PASS" if can_fail
                                else f"FAIL: {why} — verifies nothing")

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
                        existing: set[str] | None = None,
                        *, grader_refusals: set[str] | None = None) -> dict[str, Any]:
    """Screen a batch. The refusal witness is built first: every chain-backed
    ok=false input anywhere in the batch (plus any supplied history) witnesses
    that its grader CAN refuse, so an all-pass row is admissible only alongside
    that evidence. Reports admitted/rejected and the honest recirculation
    ceiling 1/(1-r) where r is the fraction rejected purely as duplicates."""
    refusals: set[str] = set(grader_refusals or set())
    for row in rows:
        if _chain_backed(row)[0]:
            refusals |= {g.get("actor")
                         for g in row.get("oracle", {}).get("grade_inputs", [])
                         if g.get("ok") is False}
    seen: set[str] = set(existing or set())
    admitted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    dup_rejections = 0
    for row in rows:
        r = screen_trajectory(row, seen, grader_refusals=refusals)
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
        "grader_refusals_witnessed": sorted(refusals),
        "admitted_rows": admitted,
        "rejected_rows": rejected,
    }
