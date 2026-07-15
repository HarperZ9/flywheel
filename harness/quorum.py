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
(different checks, different implementations, e.g. a symbolic oracle plus a
property-based fuzzer plus a differential re-run). N copies of the same
deterministic oracle agree trivially and gain nothing, and the receipt makes that
visible (distinct_members) rather than hiding it. NO LEARNED VERDICT sits in this
accept path: a member that declares itself learned (a model-graded judge) is
refused at construction, because the invariant is that an external check, never a
model, disposes. A learned judge is an advisory signal offline, not a peer here.
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
    votes: list[dict] = field(default_factory=list)     # per-verifier {type, passed, output_hash, ref}
    n_pass: int = 0
    n_total: int = 0
    threshold: float = 0.5
    quorum_needed: int = 0
    dissenters: list[str] = field(default_factory=list)  # verifiers whose vote != the accept outcome
    distinct_members: int = 0    # distinct (type, ref) identities; < n_total means a stacked ballot

    def accountability_receipt(self) -> str:
        stacked = (f"; STACKED BALLOT: {self.distinct_members} distinct of "
                   f"{self.n_total} members" if self.distinct_members
                   and self.distinct_members < self.n_total else "")
        return (f"quorum {self.n_pass}/{self.n_total} pass "
                f"(needed {self.quorum_needed}, threshold {self.threshold}) -> "
                f"{'ACCEPT' if self.passed else 'REJECT'}"
                + (f"; dissent: {','.join(self.dissenters)}" if self.dissenters else "")
                + stacked)


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
        learned = [getattr(o, "oracle_type", "?") for o in oracles
                   if getattr(o, "learned", False)]
        if learned:
            raise ValueError(
                f"no learned verdict sits in the accept path: refusing "
                f"quorum members {learned}. A model-graded judge is an "
                "advisory signal offline, never a peer that disposes.")
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
        members = []
        for o in self.oracles:
            r = o.verify(candidate, task)
            t = getattr(o, "oracle_type", "?")
            # ref = the member's endpoint/model identity; falls back to the
            # object id so distinct objects are never conflated, but two
            # wrappers over the SAME endpoint share a model_ref and collapse
            ref = getattr(o, "model_ref", "") or ("obj:" + hex(id(o)))
            members.append((t, r, ref))
        # a vote now carries the member's identity (type, ref, output_hash):
        # one endpoint under two names, or one verifier counted twice, is
        # no longer byte-identical to two independent peers
        votes = [{"type": t, "passed": bool(r.passed),
                  "output_hash": r.output_hash, "ref": ref}
                 for t, r, ref in members]
        n = len(members)
        n_pass = sum(1 for _, r, _ in members if r.passed)
        needed = self._quorum_needed(n)
        accepted = n_pass >= needed
        # identity is the ENDPOINT (model_ref), not the wrapper name: two
        # oracle_type names over one endpoint are one model voting twice
        distinct = len({ref for _, _, ref in members})
        # dissenters = the voices against the OUTCOME, not a bare majority: at
        # a supermajority threshold a 3/5 pass is still a REJECT, so the PASS
        # voters are the dissent. Under unanimity the lone FAIL is the decisive
        # veto; either way the receipt records who stood against the verdict.
        dissenters = [t for t, r, _ in members if bool(r.passed) != accepted]
        blob = json.dumps([[t, bool(r.passed), r.output_hash, ref]
                           for t, r, ref in members], sort_keys=True)
        return QuorumResult(
            passed=accepted, cmd=self.model_ref,
            output_hash=hashlib.sha256(blob.encode()).hexdigest()[:16],
            stdout_excerpt="; ".join(f"{t}:{'P' if r.passed else 'F'}" for t, r, _ in members),
            rc=0 if accepted else 1,
            votes=votes, n_pass=n_pass, n_total=n, threshold=self.threshold,
            quorum_needed=needed, dissenters=dissenters, distinct_members=distinct)
