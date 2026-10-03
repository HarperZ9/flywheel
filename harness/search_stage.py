"""search_stage.py -- the loop's search mode: who selects, who decides, what the receipt says.

When a task carries a held-out command, the visible suite selects a candidate
and the held-out suite decides on that one pick. When it carries none, the one
oracle both selects and decides, and the search stage payload says
`selection: self-scored`, so no reader mistakes the result for a held-out check.
"""
from __future__ import annotations

import hashlib
from dataclasses import replace

from .chain import append_stage
from .integrity import GuardedOracle
from .oracle import OracleResult, PytestOracle
from .proposer import ProposerOutput, prompt_hash
from .search import DEFAULT_TEMPS, best_of_n


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _timeout(oracle) -> int:
    for obj in (oracle, getattr(oracle, "base", None)):
        value = getattr(obj, "timeout", None)
        if isinstance(value, int):
            return value
    return 60


def search_oracles(task, oracle):
    """(selector, decider). The decider is None when the task has no held-out command."""
    if not getattr(task, "held_out_cmd", ""):
        return oracle, None
    timeout = _timeout(oracle)
    select = GuardedOracle(PytestOracle(timeout=timeout))
    decide = GuardedOracle(PytestOracle(timeout=timeout, cmd_attr="held_out_cmd"))
    return select, decide


def _candidate_payload(sr) -> list:
    return [{"temp": c.temperature,
             "candidate_hash": _short_hash(c.text),
             "verdict": c.oracle_result.verdict() if c.oracle_result else "NONE",
             "oracle_output_hash": c.oracle_result.output_hash if c.oracle_result else ""}
            for c in sr.candidates]


def run_search_stage(task, prompt, proposer, oracle, search, chain, **search_kw):
    """Run best-of-N, append the search stage, return (output, oracle result, budget)."""
    select, decide = search_oracles(task, oracle)
    sr = best_of_n(replace(task, prompt=prompt), proposer, select,
                   temps=(search.temps or DEFAULT_TEMPS), decide=decide, **search_kw)
    winner = sr.selected or sr.candidates[0]
    out = ProposerOutput(text=winner.text, model_ref=winner.model_ref,
                         seed=winner.seed, prompt_hash=winner.prompt_hash, cache="search")
    orc = sr.decision or winner.oracle_result or OracleResult(
        passed=False, cmd=task.oracle_cmd, output_hash="", stdout_excerpt="", rc=1)
    payload = {"n": len(sr.candidates), "correlation": round(sr.correlation, 3),
               "candidates": _candidate_payload(sr), "selection": sr.selection}
    if sr.decision is not None:
        payload["decision"] = {"verdict": sr.decision.verdict(),
                               "oracle_output_hash": sr.decision.output_hash}
    append_stage(chain, "search", prompt_hash(prompt), _short_hash(winner.text),
                 sr.verdict, payload=payload)
    calls = len(sr.candidates) + (1 if sr.decision is not None else 0)
    budget = {"candidates": len(sr.candidates), "oracle_calls": calls,
              "proposer_cache": "search"}
    return out, orc, budget
