"""companion.py -- the companion seat (SUPERAPP.md increment 5): answer locally,
escalate only the hard slice, on evidence.

The seat is the thin routing wrapper around the selection core (`AdaptiveSelector`,
already built and hardened). For each task it decides WHERE the answer comes from,
cheapest-first:

  1. proof-cache HIT  -> answer at ~0 cost with the stored, re-checkable receipt.
  2. local, verified  -> AdaptiveSelector runs the local model; an external ORACLE
                         accepts (verdict PASS) or a productive behavioral consensus
                         agrees (CONSENSUS_PASS, agreement not verification).
  3. ESCALATE         -> the loop exhausted its budget below confidence; route to a
                         costlier frontier endpoint. This is the ESCALATE VERDICT
                         (a thresholded confidence), never a learned difficulty guess.

No learned model sits on the accept path: the oracle disposes when present, else
deterministic consensus decides, and escalation is a verdict, not a prediction.
Every routing decision is appended to a ledger so the seat carries a record of
what it answered locally vs escalated, and why. The cache is duck-typed
(`.get(key)`/`.put(key, ...)`) so a real proof_cache or a stub both plug in.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .adaptive_select import AdaptiveSelector
from .selector import ACCEPT_VERDICTS

CACHE = "cache"
LOCAL_VERIFIED = "local-verified"
LOCAL_CONSENSUS = "local-consensus"
ESCALATE = "escalate"


@dataclass
class CompanionResult:
    source: str                       # cache | local-verified | local-consensus | escalate
    text: str | None                  # the answer, or None on escalate (no local accept)
    receipt: dict
    escalate_to: str | None = None    # the frontier endpoint to route to, if escalating
    best_effort_text: str | None = None   # the unverified local attempt (for the ledger)

    def to_dict(self) -> dict:
        return {"schema": "flywheel.companion-result/v1", "source": self.source,
                "escalate_to": self.escalate_to, "receipt": self.receipt}


def _task_key(task, solution_sig: str) -> str:
    return f"{getattr(task, 'task_id', '')}|{getattr(task, 'prompt', '')[:200]}|{solution_sig[:120]}"


class CompanionSeat:
    """Route a task: cache -> local verified selection -> escalate. Composes the
    AdaptiveSelector; the oracle (or deterministic consensus) is the accept
    authority; escalation is a verdict. Records every decision in `ledger`."""

    def __init__(self, proposer, *, oracle=None, cache=None,
                 escalation_endpoint: str = "anthropic",
                 initial_n: int = 4, max_n: int = 32,
                 confidence_threshold: float = 0.5, workspace_lens=None):
        self.proposer = proposer
        self.oracle = oracle
        self.cache = cache
        self.escalation_endpoint = escalation_endpoint
        self.selector = AdaptiveSelector(
            proposer, initial_n=initial_n, max_n=max_n,
            confidence_threshold=confidence_threshold)
        self.workspace_lens = workspace_lens
        self.ledger: list[dict] = []

    def _record(self, result: CompanionResult) -> CompanionResult:
        self.ledger.append({"n": len(self.ledger) + 1, **result.to_dict()})
        return result

    def answer(self, task, *, solution_sig: str = "") -> CompanionResult:
        # 1. proof-cache: a verified fact answered locally at ~0 cost.
        if self.cache is not None:
            try:
                hit = self.cache.get(_task_key(task, solution_sig))
            except Exception:
                hit = None
            if hit and self._cache_hit_valid(task, hit):
                return self._record(CompanionResult(
                    CACHE, hit.get("text"), hit.get("receipt", {})))

        # 2. local, verified selection (the AdaptiveSelector raise-N loop).
        res = self.selector.select(task, solution_sig=solution_sig, oracle=self.oracle)
        verdict = res.receipt.verdict
        if verdict == "PASS":                       # external oracle accepted
            out = CompanionResult(LOCAL_VERIFIED, res.text, res.receipt.to_dict())
            self._maybe_cache(task, solution_sig, out)
            return self._record(out)
        if verdict == "CONSENSUS_PASS":             # behavioral agreement, not verified
            return self._record(CompanionResult(
                LOCAL_CONSENSUS, res.text, res.receipt.to_dict(),
                best_effort_text=res.best_effort_text))

        # 3. escalate: budget exhausted below confidence -> a costlier tier.
        return self._record(CompanionResult(
            ESCALATE, None, res.receipt.to_dict(),
            escalate_to=self.escalation_endpoint,
            best_effort_text=res.best_effort_text))

    def _cache_hit_valid(self, task, hit) -> bool:
        """A proof-cache hit is served ONLY if it still re-checks NOW -- mirroring
        proof_cache.proof_lookup ('never blind-trusted, never stale'). With an
        oracle present, re-run it on the cached text; a hit that no longer passes
        (external state drifted) is discarded and the seat does a fresh verified
        selection. With no oracle to re-check, a stored answer is NOT trusted as a
        verified fact -- the hit is ignored. The cache is a memo of a re-checkable
        verdict, never a bypass of the check (C2)."""
        if self.oracle is None:
            return False
        try:
            return bool(self.oracle.verify(hit.get("text", ""), task).passed)
        except Exception:
            return False

    def _maybe_cache(self, task, solution_sig, out: CompanionResult) -> None:
        if self.cache is not None and out.text is not None:
            try:
                self.cache.put(_task_key(task, solution_sig),
                               {"text": out.text, "receipt": out.receipt})
            except Exception:
                pass
