"""reconcile.py -- V4: the reconcile decision lattice.

The reconcile loop walks canon's managed surfaces and decides, per surface,
whether a byte-drift is a safe mechanical fast-forward or a conflict a human must
adjudicate. The discriminator is the V3->V4 hard edge: the fast-forward-vs-conflict
call consumes the external crucible persona drift verdict, not a self-report. A
byte-drift whose scope carries a persona whose basis is no longer sound is a
conflict; a byte-drift with a sound or absent persona basis is a fast-forward.

This module holds the pure pieces of that decision, clock-free and IO-free:
- persona_fold lifts V3's single-persona fold (D-46) to a set of personas: any
  proven drift folds to DRIFT, else any honest null folds to UNVERIFIABLE, else
  MATCH, and an empty set folds to a distinct NONE.
- classify is the total lattice over (surface-drift verdict, persona fold). Every
  known combination maps to one classification, and an input outside either
  closed vocabulary fails closed to REFUSED (reported, never written, never a
  spurious human gate).

The gate overlay, the contributing-persona selection, and the two-phase
orchestrator build on these; the pure lattice proves in isolation first.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from canon.drift import (
    VERDICT_DRIFT,
    VERDICT_MATCH,
    VERDICT_MISSING,
    VERDICT_OFF_LIMITS,
    VERDICT_REFUSED,
    surface_drift,
)
from canon.persona_thesis import (
    DRIFT,
    MATCH,
    UNVERIFIABLE,
    CrucibleAssessor,
    DriftVerdict,
    assess_persona,
)
from canon.reconcile_gate import (
    ACTION_WRITE,
    PENDING,
    GateRead,
    reconcile_action,
    resolve_with_deadline,
)
from canon.registry import Surface, pool_for, resolve_surface_path
from canon.schema import (
    KIND_PERSONALITY_BLOCK,
    KIND_SYNTHESIZED_PERSONA_L3,
    SCOPE_GLOBAL,
    Record,
)

# The persona fold headline for a scope with no persona at all. The three
# non-empty folds reuse persona_thesis's verdict strings (MATCH / DRIFT /
# UNVERIFIABLE); NONE is canon's own, distinct from "no drift measured".
FOLD_NONE = "none"

# The reconcile classifications. off-limits, missing, and refused reuse drift.py's
# verdict strings unchanged (the classification IS that verdict passing through);
# in-sync, fast-forward, conflict, and held are canon's own.
IN_SYNC = "in-sync"
FAST_FORWARD = "fast-forward"
CONFLICT = "conflict"
HELD = "held"
# A conflict or held surface a raised gate approved: canon writes the fresh
# render despite the eroded basis, on a human's recorded say-so.
OVERRIDDEN = "overridden"
REFUSED = VERDICT_REFUSED
SKIP_OFF_LIMITS = VERDICT_OFF_LIMITS
SKIP_MISSING = VERDICT_MISSING

# The base classifications a human gate can overlay. A fast-forward writes on its
# own; a skip or refusal never gates; only these two ask a human to adjudicate.
_GATED = frozenset({CONFLICT, HELD})

# The fast-forward-vs-conflict decision for a byte-drifted surface, keyed on the
# persona fold. A sound or absent basis fast-forwards; an honest null holds; a
# proven drift conflicts. An unrecognized fold falls through to REFUSED.
_DRIFT_BY_FOLD = {
    FOLD_NONE: FAST_FORWARD,
    MATCH: FAST_FORWARD,
    UNVERIFIABLE: HELD,
    DRIFT: CONFLICT,
}


def persona_fold(verdicts: Iterable[DriftVerdict]) -> str:
    """Fold a scope's persona verdicts into one headline, D-46 across personas.

    A proven drift on any persona outranks everything: the basis for that scope's
    text is no longer sound. Absent a drift, any honest null keeps the whole fold
    unverifiable. Only when every persona's basis is sound does the fold read
    MATCH. An empty set folds to NONE, distinct from a measured all-clear: there
    was no basis to measure.
    """
    headlines = {v.verdict for v in verdicts}
    if not headlines:
        return FOLD_NONE
    if DRIFT in headlines:
        return DRIFT
    if UNVERIFIABLE in headlines:
        return UNVERIFIABLE
    return MATCH


def classify(drift: str, persona: str) -> str:
    """Map a surface's drift verdict and persona fold to one classification.

    Total by construction. A matching surface is in-sync whatever the persona,
    since an in-sync surface has no write decision for the persona verdict to
    discriminate. A byte-drift dispatches on the persona fold through the hard
    edge. off-limits and missing are benign skips; refused is a structural fault.
    A verdict or fold outside its closed vocabulary is a wiring fault that fails
    closed to REFUSED, never to a write and never to a spurious human gate.
    """
    if drift == VERDICT_MATCH:
        return IN_SYNC
    if drift == VERDICT_OFF_LIMITS:
        return SKIP_OFF_LIMITS
    if drift == VERDICT_MISSING:
        return SKIP_MISSING
    if drift == VERDICT_REFUSED:
        return REFUSED
    if drift == VERDICT_DRIFT:
        return _DRIFT_BY_FOLD.get(persona, REFUSED)
    return REFUSED


def contributing_personas(surface: Surface, pool: list[Record]) -> list[Record]:
    """The synthesized-persona-l3 records whose basis underlies a surface's bytes.

    Mirrors the block render contribution exactly, so the health leg measures the
    same worldview the surface renders. pool_for applies the authored-split first
    (a workspace surface with a global sibling carries only workspace-authored
    records, the globals living in that sibling file), then the layering scope
    filter drops non-global records for a global surface (a global surface renders
    only global blocks). What survives, of the persona kind, is the basis for this
    surface's bytes. Scope-coarse by D-53: a persona couples to a surface by
    scope, not by any per-block authorship canon does not track.
    """
    candidates = pool_for(surface, pool)
    if surface.scope == SCOPE_GLOBAL:
        candidates = [r for r in candidates if r.scope == SCOPE_GLOBAL]
    return [r for r in candidates if r.kind == KIND_SYNTHESIZED_PERSONA_L3]


def persona_health(surface: Surface, pool: list[Record], *,
                   assess: CrucibleAssessor) -> list[DriftVerdict]:
    """Assess the basis health of every persona that gates this surface.

    The gating set is scope-coupled (contributing_personas), but each persona's
    basis resolves against the whole pool: a persona's sources can live at any
    scope, so the measurement never narrows to the gating subset. Returns one
    DriftVerdict per gating persona, in the pool's order, and an empty list when
    no persona gates the surface, which folds to NONE, never a fabricated MATCH.
    """
    return [assess_persona(persona, pool=pool, assess=assess)
            for persona in contributing_personas(surface, pool)]


@dataclass(frozen=True, slots=True)
class SurfaceReconcile:
    """One surface's reconcile verdict: the classification and everything the
    commit phase and the witness read off it. `path` is the resolved host path
    (the commit writes there); `drift`, `persona_fold`, and `personas` are the
    evidence the classification rests on; `needs_gate` is True only when the
    commit phase must raise a fresh gate; `resolution` carries a consulted gate's
    final resolution (None when no gate was read). `expected_sha256` and
    `actual_sha256` are the drift check's region hashes (the rendered interior
    and the on-disk interior), set on a match or a drift and None on a skip or a
    refusal, so the witness binds each surface to content, not a self-report."""

    surface: Surface
    path: str
    classification: str
    drift: str
    persona_fold: str
    personas: tuple[DriftVerdict, ...]
    needs_gate: bool
    resolution: str | None
    expected_sha256: str | None
    actual_sha256: str | None


def gate_key(surface: Surface) -> dict:
    """The path-clean identity a gate is filed under: the surface's harness,
    scope, and relative path, never an absolute host path, so a gate raised on
    one machine resolves on another. Shared by the reader here and the orchestrator
    that raises the gate, so a raise and its later resume agree on the identity."""
    return {"harness": surface.harness, "scope": surface.scope,
            "path": surface.relative_path}


def _apply_gate(base: str, surface: Surface, *, gate_read: GateRead,
                now: float):
    """Overlay a raised gate onto a base classification.

    A base that is not a conflict or held never consults a gate. A gated base
    with no gate raised yet stays as it is and flags needs_gate, so the commit
    phase raises one. A gated base with a gate on file folds the frozen deadline
    and on_expiry -- read straight off the gate record, never off a live policy
    that may since have changed -- against `now`: an approval (direct, or a lapse
    the frozen on_expiry approves) overrides to a write; anything else holds the
    base. Either way the gate already exists, so it is never re-raised.

    The lapse terms are read by direct index, not with a live-policy fallback, so
    a materialized reply missing its frozen deadline or on_expiry is a loud wiring
    fault, not a silent borrow of current state; only the resolution defaults, to
    PENDING, since a freshly raised gate carries no decision yet. A resolution
    outside the vocabulary likewise raises from reconcile_action.
    """
    if base not in _GATED:
        return base, False, None
    reply = gate_read(gate_key(surface))
    if reply is None:
        return base, True, None
    if "deadline" not in reply or "on_expiry" not in reply:
        raise ValueError(
            "a materialized gate reply must carry its frozen deadline and "
            f"on_expiry; got keys {sorted(reply)}")
    resolution = resolve_with_deadline(
        reply.get("resolution", PENDING),
        deadline=reply["deadline"],
        now=now,
        on_expiry=reply["on_expiry"])
    if reconcile_action(resolution) == ACTION_WRITE:
        return OVERRIDDEN, False, resolution
    return base, False, resolution


def classify_surface(surface: Surface, pool: list[Record], *, home: str,
                     workspace: str, read_text, assess: CrucibleAssessor,
                     gate_read: GateRead, now: float = 0) -> SurfaceReconcile:
    """Classify one surface's reconcile state, the pure per-surface leg.

    The drift check scores canon-owned bytes against the personality-block subset
    of the pool -- the only records a surface renders -- which also keeps
    surface_drift total (a persona in the pool cannot raise a layering fault
    here). The crucible persona verdict is folded in only on a byte-drift, the
    sole fork where the fold changes the write decision: an in-sync surface, a
    skip, or a refusal never runs the assessor. A gate overlay then adjudicates a
    conflict or a held surface, reading the gate's own frozen lapse terms rather
    than any live policy. Read-only: it reads the host and a gate, and never
    writes or raises a gate itself.
    """
    path = resolve_surface_path(surface, home=home, workspace=workspace)
    blocks = [r for r in pool if r.kind == KIND_PERSONALITY_BLOCK]
    scored = surface_drift(surface, blocks, home=home, workspace=workspace,
                           read_text=read_text)
    drift = scored.verdict
    if drift == VERDICT_DRIFT:
        personas = tuple(persona_health(surface, pool, assess=assess))
        fold = persona_fold(personas)
    else:
        personas = ()
        fold = FOLD_NONE
    classification, needs_gate, resolution = _apply_gate(
        classify(drift, fold), surface, gate_read=gate_read, now=now)
    return SurfaceReconcile(surface=surface, path=path,
                            classification=classification, drift=drift,
                            persona_fold=fold, personas=personas,
                            needs_gate=needs_gate, resolution=resolution,
                            expected_sha256=scored.expected_sha256,
                            actual_sha256=scored.actual_sha256)
