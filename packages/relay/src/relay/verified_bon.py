"""verified_bon.py -- verified best-of-N: pick the winner by proof, not a judge.

Test-time compute scales by running a goal N times; everyone then picks the winner
with a judge model or a vote. relay picks it with a TOTAL ORDER over each run's own
re-derivable facts -- chain intact, receipts re-derive, the check was not gamed, the
integrity scan is clean, reviewability, no unbacked prior-work claim -- and records
the selection as a hash-chained meta-ledger a stranger re-runs to confirm the right
run won and why.

The order is what makes this a moat: a higher-scoring run that made its tests pass
by editing the grader ranks BELOW an honest run that failed, because ``check_trusted``
outranks the score. A leaderboard-maximizer will not ship a selector that can lower
its own headline number; and the order key is only computable over a re-derivable
chain competitors do not keep.

Honest null: the proof order is decisive only in an oracle-bearing domain (a runnable
acceptance ``check`` exists). With no check it collapses to the chain / receipt /
integrity / reviewability axes, which rank ACCOUNTABILITY, not capability.
"""
from __future__ import annotations

import json

from .local_loop import run_agent
from .local_session import SessionLedger

SCHEMA = "relay.verified-bon/v1"


def order_key(result: dict) -> list:
    """The total order over a run's re-derivable facts; higher is better. Accountability
    dominates capability: a gamed pass (check_trusted False) sinks below an honest fail."""
    return [
        bool(result.get("verified")),
        bool(result.get("check_trusted", True)),
        bool(result.get("accepted")),
        bool(result.get("integrity", {}).get("clean", True)),
        float(result.get("review", {}).get("reviewability", 0.0)),
        -int(result.get("intent_audit", {}).get("critical", 0)),
    ]


def rank(results: list) -> list:
    """Indices best-first. Stable, so ties keep run order (the earlier/cheaper run wins)."""
    return sorted(range(len(results)), key=lambda i: order_key(results[i]), reverse=True)


def build_selection_ledger(results: list, winner: int) -> SessionLedger:
    """A witnessed record of the selection: one entry per candidate (its key +
    checkpoint) and the verdict, hash-chained so the selection itself is tamper-evident."""
    meta = SessionLedger()
    meta.append("user", json.dumps({"select_best_of": len(results)}, sort_keys=True))
    for i, r in enumerate(results):
        meta.append("candidate", json.dumps(
            {"idx": i, "key": order_key(r), "checkpoint": r.get("checkpoint", ""),
             "chain_ok": bool(r.get("chain_ok"))}, sort_keys=True), {"idx": i})
    meta.append("selection", json.dumps(
        {"winner": winner, "key": order_key(results[winner]), "n": len(results)}, sort_keys=True))
    return meta


def select_best_from(results: list) -> dict:
    """Pure selection over a list of run results. Returns the winner index, the full
    order, and the witnessed selection meta-ledger."""
    if not results:
        raise ValueError("no candidate runs to select from")
    order = rank(results)
    winner = order[0]
    return {"schema": SCHEMA, "winner": winner, "order": order,
            "winning_key": order_key(results[winner]),
            "meta_ledger": build_selection_ledger(results, winner)}


def verify_selection(meta_ledger: SessionLedger, results: list) -> bool:
    """Re-derive the selection from the candidate results: the meta-ledger chain holds,
    every candidate run's own chain re-derives and matches its recorded checkpoint, and
    the recorded winner is the argmax of the re-derived order. A byte flipped in the
    winning run's ledger breaks its chain and refutes the selection."""
    if not meta_ledger.verify():
        return False
    selection = [e for e in meta_ledger.entries if e.kind == "selection"]
    if not selection:
        return False
    recorded_winner = json.loads(selection[-1].content).get("winner")
    if recorded_winner != rank(results)[0]:
        return False
    for entry in meta_ledger.entries:
        if entry.kind != "candidate":
            continue
        rec = json.loads(entry.content)
        ledger = results[rec["idx"]].get("ledger")
        if ledger is None:
            continue
        if not ledger.verify() or ledger.checkpoint() != rec["checkpoint"]:
            return False
    return True


def select_best(make_agent, goal: str, make_executor, *, n: int = 4,
                max_steps: int = 6, check: "str | None" = None, base_seed: int = 0) -> dict:
    """Run ``goal`` N times (each a fresh agent + executor, varied seed) and select the
    verified winner. ``make_agent(seed)`` and ``make_executor()`` are factories so each
    candidate is independent. Returns select_best_from's dict plus the raw results."""
    results = []
    for i in range(max(1, n)):
        ledger = SessionLedger()
        results.append(run_agent(make_agent(base_seed + i), goal, make_executor(),
                                 ledger, max_steps=max_steps, check=check))
    out = select_best_from(results)
    out["results"] = results
    return out
