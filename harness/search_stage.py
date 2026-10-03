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


def _candidate_payload(sr, checked=None) -> list:
    rows = [{"temp": c.temperature,
             "candidate_hash": _short_hash(c.text),
             "verdict": ("PRUNED" if c.pruned else
                         c.oracle_result.verdict() if c.oracle_result else "NONE"),
             "oracle_output_hash": c.oracle_result.output_hash if c.oracle_result else ""}
            for c in sr.candidates]
    if checked is not None:
        for row, c in zip(rows, sr.candidates):
            row["checks"] = [{"check": r["check"], "verdict": r["verdict"], "code": r["code"]}
                             for r in checked.receipts_for(c.text)]
    return rows


def _cost_floor(sr, search) -> dict:
    """Per-candidate cost receipts and their summary; candidates without timing
    or provider token counts are counted, never guessed."""
    from .cost_floor import ModelProfile, receipt, summarize
    model = ModelProfile(**(search.model_profile or {}))
    rows, missing = [], 0
    for c in sr.candidates:
        usage = c.usage or {}
        if c.generation_duration_ns is None or usage.get("completion") is None:
            missing += 1
            continue
        rows.append(receipt(c.generation_duration_ns / 1e9, int(usage.get("prompt") or 0),
                            int(usage["completion"]), model, search.hardware))
    return {"summary": summarize(rows), "receipts": rows, "untimed_candidates": missing}


def run_search_stage(task, prompt, proposer, oracle, search, chain, **search_kw):
    """Run best-of-N, append the search stage, return (output, oracle result, budget)."""
    select, decide = search_oracles(task, oracle)
    checked = None
    if getattr(search, "checks", None):
        from .checks.adopt import CheckedOracle
        select = checked = CheckedOracle(select, search.checks)
    if getattr(search, "hardware", None):
        search_kw.setdefault("collect_detail", True)
    sr = best_of_n(replace(task, prompt=prompt), proposer, select,
                   temps=(search.temps or DEFAULT_TEMPS), decide=decide,
                   prune_m=getattr(search, "prune_m", None),
                   effort_gate=getattr(search, "effort_gate", "off"), **search_kw)
    winner = sr.selected or sr.candidates[0]
    out = ProposerOutput(text=winner.text, model_ref=winner.model_ref,
                         seed=winner.seed, prompt_hash=winner.prompt_hash, cache="search")
    orc = sr.decision or winner.oracle_result or OracleResult(
        passed=False, cmd=task.oracle_cmd, output_hash="", stdout_excerpt="", rc=1)
    payload = {"n": len(sr.candidates), "correlation": round(sr.correlation, 3),
               "candidates": _candidate_payload(sr, checked), "selection": sr.selection}
    if getattr(search, "prune_m", None):
        payload["pruning"] = {"m": search.prune_m, "pruned": sr.pruned,
                              "pruned_tokens": sr.pruned_tokens,
                              "tokens_saved": 0, "basis": "whole completions; oracle runs saved only"}
    if sr.effort_gate != "off":
        payload["effort_gate"] = {"gate": sr.effort_gate, "planned": sr.planned,
                                  "drawn": len(sr.candidates),
                                  "skipped": sr.planned - len(sr.candidates)}
    if getattr(search, "hardware", None):
        payload["cost_floor"] = _cost_floor(sr, search)
    if sr.decision is not None:
        payload["decision"] = {"verdict": sr.decision.verdict(),
                               "oracle_output_hash": sr.decision.output_hash}
    append_stage(chain, "search", prompt_hash(prompt), _short_hash(winner.text),
                 sr.verdict, payload=payload)
    calls = len(sr.candidates) - sr.pruned + (1 if sr.decision is not None else 0)
    budget = {"candidates": len(sr.candidates), "oracle_calls": calls,
              "proposer_cache": "search"}
    return out, orc, budget
