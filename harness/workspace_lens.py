"""workspace_lens.py -- DEMOTE-ONLY workspace advisory (J-space, C2-safe).

Motivated by the 2026 Jacobian-lens / J-space work (transformer-circuits) and the
"models are blind outside the J-space" follow-up: a model's self-report is
confined to a small verbalizable workspace, so behavioral consensus (agreement
among the model's own samples) cannot tell agree-and-correct from
agree-and-wrong. A workspace read can supply a signal consensus structurally
lacks -- but a lens/decoder is a model-derived judge, and C2 (HARNESS.md) forbids
a learned judge on the accept path.

The resolution, and the ONLY contract this module offers: a workspace signal is a
**DEMOTE-ONLY advisory**. It may lower confidence or turn a CONSENSUS_PASS into
LOW_CONFIDENCE (so the adaptive loop raises N or escalates); it may NEVER grant an
accept, and it never touches an oracle-VERIFIED PASS. A signal that can only add
caution never becomes an authority, so C2 stays intact by construction.

What is real here today is the SAFE SHAPE of the integration. The signal SOURCE
(reading residual-stream activations through a fitted Jacobian lens) needs
white-box access via serve.py/HF, not the ollama path, and a fitted lens for the
served model -- neither is wired. `NullLens` is the default: with no lens, the
engine behaves byte-identically to having no workspace signal at all. No claim in
the harness rides on a lens we have not fitted.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class WorkspaceCaution:
    """An advisory. `demote=True` asks the caller to lower trust in a
    consensus-only accept; `score` in [0,1] is the strength (advisory only).
    A caution can never request an ACCEPT -- there is no such field."""
    demote: bool = False
    score: float = 0.0
    reason: str = ""


NO_CAUTION = WorkspaceCaution(demote=False, score=0.0, reason="no workspace signal")


@runtime_checkable
class WorkspaceLens(Protocol):
    """Reads a workspace signal for a candidate and returns a caution. A real
    implementation transports activations through a fitted Jacobian lens; the
    default NullLens returns NO_CAUTION so the engine is unchanged."""

    def caution(self, candidate: str, *, solution_sig: str = "",
                task=None) -> WorkspaceCaution: ...


class NullLens:
    """The default. No activation access, never cautions -- the engine behaves
    identically to having no workspace signal."""

    def caution(self, candidate: str, *, solution_sig: str = "",
                task=None) -> WorkspaceCaution:
        return NO_CAUTION


class AlwaysCautionLens:
    """A test/reference lens that always cautions with a fixed reason. Useful to
    prove the demote-only wiring fires; it reads no activations."""

    def __init__(self, score: float = 1.0, reason: str = "test caution"):
        self._c = WorkspaceCaution(demote=True, score=score, reason=reason)

    def caution(self, candidate: str, *, solution_sig: str = "",
                task=None) -> WorkspaceCaution:
        return self._c
