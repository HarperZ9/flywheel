"""Consequence scope -- mediate consequence, never activity.

Over-mediation is the failure where every creative act has to pass a gate.  The
fix is to gate only actions that cross a hard-to-reverse, outward-facing boundary
(publish, export, overwrite a master, spend, delete, send, deploy) and let
everything reversible and local flow free.  Perception (the continuity loop) is
never gated at all.

This module gives a producer one cheap question -- `requires_gate(action_kind)` --
so creative tools can run frictionless and only consult the write-gate for the
rare consequential action.  The scope is the operator's dial: the default is
"consequential writes only", so it limits nothing the operator does not choose
to limit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Actions whose effects are hard to reverse or are outward-facing.  Everything
# NOT in this set is treated as reversible/local and flows without the gate.
DEFAULT_CONSEQUENTIAL = frozenset({
    "publish",
    "export",
    "overwrite",
    "delete",
    "spend",
    "send",
    "deploy",
    "release",
})


@dataclass(frozen=True)
class ConsequenceScope:
    """Which action kinds must pass the write-gate.  Reversible/local actions
    (draw, edit-draft, generate-variation, undo, preview, ...) are never gated."""

    gated_actions: frozenset = field(default_factory=lambda: DEFAULT_CONSEQUENTIAL)

    def requires_gate(self, action_kind: str) -> bool:
        return action_kind in self.gated_actions

    def with_also(self, *action_kinds: str) -> "ConsequenceScope":
        """Operator widens the gated set (stricter)."""
        return ConsequenceScope(self.gated_actions | frozenset(action_kinds))

    def without(self, *action_kinds: str) -> "ConsequenceScope":
        """Operator narrows the gated set (looser)."""
        return ConsequenceScope(self.gated_actions - frozenset(action_kinds))


def creative_profile() -> ConsequenceScope:
    """The default for creative/gamedev environments: only consequential writes
    are gated; all iteration flows free."""
    return ConsequenceScope()
