"""quorum.py — accountability to peers, not to an authority, in the accept path.

C2 says no LEARNED authority gates acceptance. This goes further: no SINGLE
authority at all. A lone verifier is still an authority — whatever it says, goes.
A QuorumOracle wraps N INDEPENDENT verifiers and accepts only when a quorum of
peers agree, recording EVERY verifier's vote so the verdict is answerable to the
peers who cast it. Dissent is heard: under unanimity, any one honest peer that
finds a real defect vetoes acceptance, even against a majority.

This is the operator's thesis (accountability to neighbours/peers drives real
growth; authority does not) made into a verification primitive, and the
perspective-diverse-verify pattern (Multi-Agent Verification, 2502.20379) made an
accept-path object rather than an offline check. It composes with the Oracle
protocol: a QuorumOracle IS an Oracle, so it drops into the loop unchanged.

Honest scope: quorum only adds signal when the verifiers are genuinely INDEPENDENT
(different checks, different implementations, a code oracle plus an LLM judge). N
copies of the same deterministic oracle agree trivially and gain nothing — the
receipt makes that visible (identical votes) rather than hiding it.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field

from .oracle import Oracle, OracleResult
from .task import Task


@dataclass
class QuorumResult(OracleResult):
    votes: list[dict] = field(default_factory=list)     # per-verifier {type, passed}
    n_pass: int = 0
    n_total: int = 0
    threshold: float = 0.5
    quorum_needed: int = 0
    dissenters: list[str] = field(default_factory=list)  # verifiers that voted against the outcome

    def accountability_receipt(self) -> str:
        return (f"quorum {self.n_pass}/{self.n_total} pass "
                f"(needed {self.quorum_needed}, threshold {self.threshold}) -> "
                f"{'ACCEPT' if self.passed else 'REJECT'}"
                + (f"; dissent: {','.join(self.dissenters)}" if self.dissenters else ""))


class QuorumOracle:
    """Accept iff at least `ceil(threshold * n)` independent verifiers vote PASS.
    threshold=1.0 -> unanimity (any peer can veto); >0.5 -> supermajority; 0.5 ->
    strict majority (needs > n/2, i.e. ceil(0.5*n)+adjust). We use
    quorum_needed = max(1, ceil(threshold * n)), and for majority semantics a tie
    does NOT reach quorum unless threshold<=0.5 rounds appropriately — see tests."""

    oracle_type = "quorum"

    def __init__(self, oracles: list[Oracle], *, threshold: float = 0.5,
                 unanimous: bool = False):
        if not oracles:
            raise ValueError("quorum needs at least one verifier")
        self.oracles = oracles
        self.threshold = 1.0 if unanimous else threshold
        self.model_ref = "quorum:" + ",".join(getattr(o, "oracle_type", "?") for o in oracles)

    def _quorum_needed(self, n: int) -> int:
        if self.threshold >= 1.0:
            return n                                     # unanimity
        # strict majority for 0.5; supermajority above it
        need = math.floor(self.threshold * n) + 1
        return min(n, max(1, need))

    def verify(self, candidate: str, task: Task) -> QuorumResult:
        results = [(getattr(o, "oracle_type", "?"), o.verify(candidate, task))
                   for o in self.oracles]
        votes = [{"type": t, "passed": bool(r.passed)} for t, r in results]
        n = len(results)
        n_pass = sum(1 for _, r in results if r.passed)
        needed = self._quorum_needed(n)
        accepted = n_pass >= needed
        # dissenters = the minority voice — verifiers who voted against the
        # majority. Under unanimity that minority is decisive (it vetoes); under
        # majority it is overruled but still recorded (answerability).
        majority_pass = n_pass * 2 > n
        dissenters = [t for t, r in results if bool(r.passed) != majority_pass]
        blob = json.dumps([[t, bool(r.passed)] for t, r in results], sort_keys=True)
        return QuorumResult(
            passed=accepted, cmd=self.model_ref,
            output_hash=hashlib.sha256(blob.encode()).hexdigest()[:16],
            stdout_excerpt="; ".join(f"{t}:{'P' if r.passed else 'F'}" for t, r in results),
            rc=0 if accepted else 1,
            votes=votes, n_pass=n_pass, n_total=n, threshold=self.threshold,
            quorum_needed=needed, dissenters=dissenters)
