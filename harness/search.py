"""search.py — M3 diversified best-of-N + correlation detector + voice-cap gate.

The pass@N amplification: sample k candidates at varied temperatures (diversity
of source, not just count), verify each, accept the first PASS. The §8 trap —
correlated-N converging to the same wrong answer looks like strong agreement but
is fake — is handled by the voice-cap gate: if no candidate passes AND the set
is correlated (wrong-attractor convergence), return UNVERIFIABLE rather than
confidently asserting FAIL. Genuine diverse failure is honest FAIL.

Falsifier (HARNESS-ROADMAP M3): on a task where correlated-N converges wrong,
diversified-N + gate either finds the right answer (diversity broke the
attractor) or returns UNVERIFIABLE — never confident-wrong.
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Protocol

from .oracle import Oracle, OracleResult
from .proposer import Proposer
from .search_prune import DuplicatePruner
from .task import Task

DEFAULT_TEMPS = [0.0, 0.4, 0.8, 1.1]
SELF_SCORED = "self-scored"
HELD_OUT_DECIDES = "visible-selects-held-out-decides"
REASONING_TEMPS = [0.5, 0.7, 0.9, 1.1]
CORRELATION_THRESHOLD = 0.85


@dataclass
class Candidate:
    text: str
    model_ref: str
    seed: int
    temperature: float
    prompt_hash: str
    oracle_result: OracleResult | None = None
    cache: str = ""
    usage: dict | None = None
    served_model: str = ""
    generation_duration_ns: int | None = None
    oracle_duration_ns: int | None = None
    pruned: bool = False

    @property
    def passed(self) -> bool:
        return self.oracle_result is not None and self.oracle_result.passed


@dataclass
class SearchResult:
    candidates: list[Candidate] = field(default_factory=list)
    accepted: Candidate | None = None
    correlation: float = 0.0
    diversified: bool = True
    verdict: str = "FAIL"  # PASS | FAIL | UNVERIFIABLE
    reason: str = ""
    # Who chose and who judged. self-scored: one oracle did both, so the
    # result cannot lose to its own selection. With a decider, `selected` is the
    # selector's pick and `decision` is the decider's one verdict on it.
    selection: str = SELF_SCORED
    selected: Candidate | None = None
    decision: OracleResult | None = None
    pruned: int = 0
    pruned_tokens: int = 0

    @property
    def accepted_text(self) -> str | None:
        return self.accepted.text if self.accepted else None


def _token_set(text: str) -> set[str]:
    return set(text.split())


def jaccard(a: str, b: str) -> float:
    sa, sb = _token_set(a), _token_set(b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)


def max_pairwise_correlation(texts: list[str]) -> float:
    if len(texts) < 2:
        return 0.0
    m = 0.0
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            m = max(m, jaccard(texts[i], texts[j]))
    return m


def best_of_n(task: Task, proposer: Proposer, oracle: Oracle, *,
              temps: list[float] | None = None,
              seeds: list[int] | None = None,
              collect_detail: bool = False,
              decide: Oracle | None = None,
              prune_m: int | None = None) -> SearchResult:
    """Sample at each temperature; `oracle` selects the first passing candidate
    in proposal order (temperature 0.0 first, so ties fall to greedy).

    With `decide`, the decider runs once, on the pick only, and its verdict is
    the result: a pick the decider rejects is FAIL, not a reason to try the next
    candidate. Without it the selector also decides, and the result says so.
    With `prune_m`, a candidate that duplicates `prune_m` earlier ones skips the
    oracle (search_prune.py).
    """
    temps = list(temps or DEFAULT_TEMPS)
    n = len(temps)
    seeds = seeds or [task.seed + i for i in range(n)]
    res = SearchResult(diversified=len(set(temps)) > 1)
    pruner = DuplicatePruner(prune_m) if prune_m else None
    for i, (t, s) in enumerate(zip(temps, seeds)):
        gen_start = time.perf_counter_ns()
        out = proposer.generate(
            task.prompt, seed=s, temperature=t,
            max_new_tokens=task.max_new_tokens, system=task.system)
        gen_ns = time.perf_counter_ns() - gen_start
        if pruner is not None and pruner.check(out.text):
            res.candidates.append(_pruned(out, s, t, res))
            continue
        oracle_start = time.perf_counter_ns()
        orc = oracle.verify(out.text, task)
        oracle_ns = time.perf_counter_ns() - oracle_start
        c = Candidate(text=out.text, model_ref=out.model_ref, seed=s,
                      temperature=t, prompt_hash=out.prompt_hash,
                      oracle_result=orc)
        if collect_detail:
            c.cache = out.cache
            c.usage = out.usage
            c.served_model = out.served_model
            c.generation_duration_ns = gen_ns
            c.oracle_duration_ns = oracle_ns
        res.candidates.append(c)
        if c.passed and res.accepted is None:
            res.accepted = c
    texts = [c.text for c in res.candidates]
    res.correlation = max_pairwise_correlation(texts)
    res.selected = res.accepted
    if decide is not None:
        return _decide(res, decide, task)
    if any(c.passed for c in res.candidates):
        res.verdict = "PASS"
        res.reason = "at least one candidate passed the oracle"
        return res
    return _no_pass(res)


def _pruned(out, seed: int, temp: float, res: SearchResult) -> Candidate:
    res.pruned += 1
    res.pruned_tokens += int((out.usage or {}).get("completion_tokens")
                             or len(out.text.split()))
    return Candidate(text=out.text, model_ref=out.model_ref, seed=seed,
                     temperature=temp, prompt_hash=out.prompt_hash, pruned=True)


def _no_pass(res: SearchResult) -> SearchResult:
    if res.correlation >= CORRELATION_THRESHOLD:
        res.verdict = "UNVERIFIABLE"
        res.reason = (f"no pass and candidates correlated "
                      f"(max jaccard {res.correlation:.2f} >= "
                      f"{CORRELATION_THRESHOLD}) — wrong-attractor "
                      f"convergence suspected, refusing confident FAIL")
    else:
        res.verdict = "FAIL"
        res.reason = (f"no pass and candidates diverse "
                      f"(max jaccard {res.correlation:.2f}) — honest failure")
    return res


def _decide(res: SearchResult, decide: Oracle, task: Task) -> SearchResult:
    res.selection = HELD_OUT_DECIDES
    if res.selected is None:
        return _no_pass(res)
    res.decision = decide.verify(res.selected.text, task)
    if res.decision.verdict() == "PASS":
        res.verdict = "PASS"
        res.reason = "the selector's pick passed the held-out decider"
    else:
        res.accepted = None
        res.verdict = "FAIL"
        res.reason = ("the selector's pick failed the held-out decider "
                      f"({res.decision.verdict()}); no other candidate is tried")
    return res
