"""data_flywheel.py — measure the systems-efficiency answer to "A Stargate for Data".

Depue's sharpest near-term point: RL is running out of gradable tasks. This
module measures what the verified-inference loop already does about it — it
MANUFACTURES gradable data — and quantifies the data-efficiency the flywheel
buys, honestly, against the amortization ceiling.

Two measured claims, both re-derivable (see VERIFIED-DATA-FLYWHEEL.md):

  1. MANUFACTURED YIELD. Every curated task is a gradable RL datum carrying its
     own witness: (prompt, solution, oracle). Unlike a scraped token, its verdict
     is re-checkable. The corpus is a data factory whose output is verifiable by
     construction.

  2. CRITERION CONSERVATION (transpile-conservation, applied to RL data). What
     makes a datum GRADABLE is its oracle (the hidden tests) — that is the scarce,
     valuable invariant. The solution is the expensive part in tokens, and it is
     REGENERABLE by a model from the prompt+oracle. So a verified corpus can store
     the criterion and regenerate solutions on demand: it conserves the
     gradable-invariant at a fraction of the tokens. This module measures that
     fraction over a real task set.

Honest ceiling (never omitted): recirculation amortizes; it does not create
novel coverage. The report carries the reuse-bounded amortization ceiling from
asymmetry.py so no "infinite data" reading survives.

Token counts are a stated word/punct estimate; the RATIO is estimator-robust.
"""
from __future__ import annotations

import re

_TOK = re.compile(r"\w+|[^\w\s]")


def estimate_tokens(text: str) -> int:
    return len(_TOK.findall(text or ""))


def _spec_fields(spec) -> tuple[str, str, str]:
    """(prompt, solution, hidden_tests) from a TaskSpec or a dict row."""
    if hasattr(spec, "prompt"):
        return spec.prompt, spec.solution, spec.hidden_tests
    return spec["prompt"], spec["solution"], spec["hidden_tests"]


def criterion_conservation(specs) -> dict:
    """Over a set of gradable tasks, measure the token split between the
    CRITERION (the oracle/tests — the gradable invariant that must be kept) and
    the SOLUTION (regenerable from prompt+criterion). A high solution share means
    a verified corpus can conserve the criterion and regenerate the rest: the
    data-efficiency the flywheel buys."""
    rows = list(specs)
    art = crit = sol = prm = 0
    per = []
    for s in rows:
        prompt, solution, tests = _spec_fields(s)
        tp, ts, tt = estimate_tokens(prompt), estimate_tokens(solution), estimate_tokens(tests)
        artifact = tp + ts + tt
        art += artifact; crit += tt; sol += ts; prm += tp
        per.append({"task": getattr(s, "task_id", None) or (s.get("task_id") if isinstance(s, dict) else None),
                    "artifact_tokens": artifact, "criterion_tokens": tt,
                    "solution_tokens": ts})
    # what a criterion-conserving store keeps = prompt + oracle (regenerate solution)
    kept = prm + crit
    return {
        "schema": "data-flywheel.criterion-conservation/1",
        "tasks": len(rows),
        "artifact_tokens": art,
        "criterion_tokens": crit,
        "solution_tokens": sol,
        "kept_if_regenerating_solutions": kept,
        "solution_share": round(sol / art, 4) if art else 0.0,
        "conservation_ratio": round(art / kept, 3) if kept else 1.0,
        "reading": ("store prompt+oracle (the gradable invariant), regenerate the "
                    "solution -> keep the criterion at 1/conservation_ratio of the "
                    "artifact tokens, with the verdict still re-checkable"),
        "token_estimator": "word+punct (ratio is estimator-robust)",
        "per_task": per,
    }


def manufactured_yield(specs, *, oracle_calls_per_task: int = 1) -> dict:
    """Every curated task is a gradable RL datum with a re-checkable oracle. This
    is synthetic data with a witness — the property scraped data lacks. Reports
    the yield and the honest amortization ceiling so no unbounded reading holds."""
    rows = list(specs)
    return {
        "schema": "data-flywheel.manufactured-yield/1",
        "gradable_triples": len(rows),          # (prompt, solution, oracle) each
        "witnessed": True,                       # every triple carries a re-checkable oracle
        "oracle_calls": len(rows) * oracle_calls_per_task,
        "vs_scraped": ("scraped tokens carry no verdict; these carry a re-checkable "
                       "oracle -> gradable by construction, not by later labeling"),
        "amortization_ceiling": ("1/(1-r), bounded by reuse fraction r; NO compounding "
                                 "on novel coverage (asymmetry.py). Recirculation "
                                 "amortizes collection, it does not replace it."),
    }
