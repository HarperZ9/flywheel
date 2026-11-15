"""Mind — a perceiver with its own sensory access. The center reconciles two of them.

A mind perceives ONE channel of the subject (its sense) and proposes; then, seeing the other's
deposit (raw perception cannot cross — only what each expresses), it reconciles. v1 ships the
INTERFACE + a deterministic StubMind so the loop runs and tests are hermetic. The live engine organs
plug in here behind the same interface: the **atelier** as a generate-mind, the **eye** as a
perceive-mind, or a model subagent (the protocol proven in DEMO-two-minds.md).
"""
from __future__ import annotations
from typing import Protocol


class Mind(Protocol):
    name: str
    channel: str  # which perceptible form this mind perceives (e.g. "text", "diagram")

    def perceive_and_propose(self, view: str) -> str:
        """Perceive this mind's channel of the subject and propose toward the telos."""
        ...

    def reconcile(self, own_view: str, others_deposits: list[str]) -> str:
        """Having seen the other minds' deposits, revise into a reconciled proposal."""
        ...


class StubMind:
    """Deterministic fake mind for hermetic tests/CLI demo. Its proposal is a function of its
    channel + the view, so two minds on different channels propose DIFFERENTLY, and the reconciled
    proposal visibly DIFFERS from either solo (the meeting is not a no-op — SC5)."""

    def __init__(self, name: str, channel: str):
        self.name = name
        self.channel = channel

    def perceive_and_propose(self, view: str) -> str:
        return f"[{self.channel}] from {self.name}: {view.strip()[:120]}"

    def reconcile(self, own_view: str, others_deposits: list[str]) -> str:
        merged = " + ".join(d.strip()[:80] for d in others_deposits)
        return f"[{self.channel}|reconciled by {self.name}] mine({own_view.strip()[:60]}) ⊕ theirs({merged})"
