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
from dataclasses import dataclass, field
from typing import Protocol

from .oracle import Oracle, OracleResult
from .proposer import Proposer
from .task import Task

DEFAULT_TEMPS = [0.0, 0.4, 0.8, 1.1]
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
              seeds: list[int] | None = None) -> SearchResult:
    temps = list(temps or DEFAULT_TEMPS)
    n = len(temps)
    seeds = seeds or [task.seed + i for i in range(n)]
    res = SearchResult(diversified=len(set(temps)) > 1)
    for i, (t, s) in enumerate(zip(temps, seeds)):
        out = proposer.generate(
            task.prompt, seed=s, temperature=t,
            max_new_tokens=task.max_new_tokens, system=task.system)
        orc = oracle.verify(out.text, task)
        c = Candidate(text=out.text, model_ref=out.model_ref, seed=s,
                      temperature=t, prompt_hash=out.prompt_hash,
                      oracle_result=orc)
        res.candidates.append(c)
        if c.passed and res.accepted is None:
            res.accepted = c
    texts = [c.text for c in res.candidates]
    res.correlation = max_pairwise_correlation(texts)
    any_pass = any(c.passed for c in res.candidates)
    if any_pass:
        res.verdict = "PASS"
        res.reason = "at least one candidate passed the oracle"
    elif res.correlation >= CORRELATION_THRESHOLD:
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
