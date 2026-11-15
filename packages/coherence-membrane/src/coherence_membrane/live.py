"""LiveMembrane -- the living loop as one configurable object.

This ties the whole read-gate together into the shape the membrane is for: a
thing that PERCEIVES continuously, REMEMBERS an authorized baseline, and mediates
ONLY consequence. It owns no authority of its own -- perception is free and
un-gated; acting routes through proof-surface's write-gate, and only for actions
the consequence-scope says are consequential.

  perceive(source)  -> change-proportional, self-throttled ContinuityEvents
  authorize(obs)    -> pin the current state as the baseline (operator's act)
  baseline_check(o) -> MATCH / DRIFT / UNVERIFIABLE vs the authorized baseline
  propose(action)   -> free (reversible/local) OR write-gate decision (consequential)

It is a convenience composition of existing parts; every guarantee still lives in
those parts (inert organs, fail-closed gate, honest drift). The orchestrator adds
no new authority and removes no check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

from .baseline import Baseline, BaselineVerdict
from .capture import CaptureSource
from .continuity import ContinuityEvent, ResourceBudget, run_continuity
from .membrane import build_gate_request, decide
from .observation import Observation
from .organ import Organ
from .phash import UNVERIFIABLE
from .scope import ConsequenceScope, creative_profile


@dataclass(frozen=True)
class LiveDecision:
    """The outcome of proposing an action through the living loop."""

    action_kind: str
    target: str
    gated: bool  # did this action need the write-gate at all?
    decision: str  # allow / deny / needs-human
    reasons: list[str] = field(default_factory=list)


class LiveMembrane:
    """An operator-configured living loop: perceive, remember, mediate consequence."""

    def __init__(
        self,
        *,
        budget: ResourceBudget | None = None,
        scope: ConsequenceScope | None = None,
        baseline: Baseline | None = None,
        organ: Organ | None = None,
    ):
        self.budget = budget or ResourceBudget()
        self.scope = scope or creative_profile()
        self.baseline = baseline
        self.organ = organ

    # --- perception (always-on, free, never blocks) -----------------------

    def perceive(self, source: CaptureSource, *, max_frames: int | None = None) -> Iterator[ContinuityEvent]:
        return run_continuity(source, budget=self.budget, organ=self.organ, max_frames=max_frames)

    # --- baseline memory (the operator authorizes a state) ----------------

    def authorize(self, observation: Observation) -> None:
        if self.baseline is None:
            self.baseline = Baseline()
        self.baseline.pin(observation)

    def baseline_check(self, observation: Observation) -> BaselineVerdict:
        if self.baseline is None:
            return BaselineVerdict(UNVERIFIABLE, None, "no baseline configured")
        return self.baseline.check(observation)

    # --- mediate consequence, never activity ------------------------------

    def propose(
        self,
        action_kind: str,
        target: str,
        *,
        authorization: dict[str, Any] | None = None,
        observation: Observation | None = None,
        drift=None,
    ) -> LiveDecision:
        """Decide whether an action may proceed.

        Reversible/local actions are NOT gated -- they return allow immediately, so
        creative flow is frictionless. Consequential actions (per the scope) are
        routed to the write-gate; with no write-gate installed that is needs-human,
        never a fabricated allow.
        """
        if not self.scope.requires_gate(action_kind):
            return LiveDecision(
                action_kind, target, gated=False, decision="allow",
                reasons=["reversible/local action; no gate required (consequence-scoped)"],
            )
        request = build_gate_request(
            action_kind=action_kind, target=target,
            authorization=authorization or {}, observation=observation, drift=drift,
        )
        result = decide(request)
        decision = result.decision if hasattr(result, "decision") else result["decision"]
        reasons = result.reasons if hasattr(result, "reasons") else result.get("reasons", [])
        return LiveDecision(action_kind, target, gated=True, decision=decision, reasons=list(reasons))
