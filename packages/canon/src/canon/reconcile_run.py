"""reconcile_run.py -- V4: the two-phase reconcile orchestrator.

reconcile walks canon's managed surfaces and brings each host file back in line
with the pool, or hands the decision to a human when it cannot. It is two-phase
by construction, and the split is the whole safety story:

- Phase one classifies every surface (classify_surface), reading only: the host
  bytes, the crucible persona verdict on a byte-drift, and any gate already on
  file. Nothing is written and no gate is raised while the run is still deciding.
- Phase two commits the decided outcomes at once: a fast-forward or an approved
  override writes its fresh render; an unresolved conflict or held surface raises
  a fresh gate whose durable deadline and on_expiry are frozen here, at raise
  time, so a later resume reads back exactly what this run decided. The run is
  witnessed once, after the commit, even when nothing changed.

Every engine touch is an injected seam (IO, the crucible assessor, the gate
reader and raiser, the run witness, the clock), so canon imports no engine and
the whole loop proves against fakes.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from canon.reconcile import (
    CONFLICT,
    FAST_FORWARD,
    HELD,
    OVERRIDDEN,
    REFUSED,
    SurfaceReconcile,
    classify_surface,
    gate_key,
)
from canon.persona_thesis import CrucibleAssessor
from canon.reconcile_gate import (
    ConflictGatePolicy,
    GateRaise,
    GateRead,
    RunWitness,
)
from canon.registry import SURFACE_CATALOG, write_surfaces
from canon.schema import KIND_PERSONALITY_BLOCK, Record

# The witness record's kind tag, the anchor a re-derivation keys on.
WITNESS_KIND = "canon_reconcile_run"

# The classifications the commit phase writes: a clean mechanical fast-forward,
# and a conflict or held surface a human gate approved.
_WRITE = frozenset({FAST_FORWARD, OVERRIDDEN})
# The classifications that keep a run from being ok: an unresolved conflict or
# held surface a human still owes, and a structural refusal. A skip is ok.
_NOT_OK = frozenset({CONFLICT, HELD, REFUSED})


@dataclass(frozen=True, slots=True)
class ReconcileReport:
    """The whole run's outcome. `ok` is False when any surface still needs a
    human (conflict or held) or hit a structural refusal. `surfaces` is every
    per-surface verdict in catalog order; `committed` is the host paths written
    this run; `gates_raised` is the frozen gate payload for each surface this run
    handed to a human; `witnessed` records whether the run was witnessed."""

    ok: bool
    surfaces: tuple[SurfaceReconcile, ...]
    committed: tuple[str, ...]
    gates_raised: tuple[dict, ...]
    witnessed: bool


def _freeze_deadline(policy: ConflictGatePolicy, now: float) -> float | None:
    """Freeze the gate's absolute deadline at raise time: the run's clock plus
    the policy window, or None when the policy is unbounded. Frozen here so a
    later resume evaluates the same deadline this run committed to, never a live
    policy that may since have changed."""
    if policy.deadline_seconds is None:
        return None
    return now + policy.deadline_seconds


def _gate_payload(sr: SurfaceReconcile, *, policy: ConflictGatePolicy,
                  now: float, run_ord: int) -> dict:
    """The durable gate record for one conflict, path-clean by gate_key and
    carrying the frozen deadline and on_expiry the resume reads back."""
    return {**gate_key(sr.surface), "classification": sr.classification,
            "persona_fold": sr.persona_fold, "run_ord": run_ord,
            "deadline": _freeze_deadline(policy, now),
            "on_expiry": policy.on_expiry}


def reconcile(pool: list[Record], *, home: str, workspace: str, read_text,
              write_text, assess: CrucibleAssessor, gate_read: GateRead,
              gate_raise: GateRaise, run_ord: int,
              policy: ConflictGatePolicy = ConflictGatePolicy(), now: float = 0,
              witness: RunWitness | None = None, surfaces=None) -> ReconcileReport:
    """Reconcile every managed surface in two phases, classify then commit.

    Phase one classifies all `surfaces` (the catalog when None) with reads only.
    Phase two writes the fast-forwards and approved overrides in one batch through
    the exact writer the drift check mirrors, raises a fresh durable gate for each
    surface that still needs a human, and witnesses the run once. The write leg
    sees only personality blocks -- the sole records a surface renders -- matching
    what the classification measured.
    """
    catalog = SURFACE_CATALOG if surfaces is None else tuple(surfaces)
    results = tuple(
        classify_surface(surface, pool, home=home, workspace=workspace,
                         read_text=read_text, assess=assess, gate_read=gate_read,
                         now=now)
        for surface in catalog)

    blocks = [r for r in pool if r.kind == KIND_PERSONALITY_BLOCK]
    to_write = tuple(sr.surface for sr in results
                     if sr.classification in _WRITE)
    committed: tuple[str, ...] = ()
    if to_write:
        written = write_surfaces(blocks, home=home, workspace=workspace,
                                 read_text=read_text, write_text=write_text,
                                 surfaces=to_write)
        committed = tuple(r.path for r in written if r.status == "written")

    gates_raised = []
    for sr in results:
        if sr.needs_gate:
            payload = _gate_payload(sr, policy=policy, now=now, run_ord=run_ord)
            gate_raise(payload)
            gates_raised.append(payload)

    ok = not any(sr.classification in _NOT_OK for sr in results)
    report = ReconcileReport(ok=ok, surfaces=results, committed=committed,
                             gates_raised=tuple(gates_raised),
                             witnessed=witness is not None)
    if witness is not None:
        witness(run_witness_payload(report, run_ord=run_ord,
                                    pool_digest=_pool_digest(pool)))
    return report


def _pool_digest(pool: list[Record]) -> str:
    """A sha256 over the pool, order-independent: every record's canonical JSON,
    sorted, joined by newline. Binds the witness to the exact record set the run
    read, so the receipt names its inputs, not only its outcomes."""
    canonical = "\n".join(sorted(r.to_json() for r in pool))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _witness_row(sr: SurfaceReconcile, committed: frozenset) -> dict:
    """One surface's witness row: its path-clean identity, the decision, and the
    region hashes that back it. `path` is the relative path, never the absolute
    host path, so the receipt travels between machines."""
    return {"harness": sr.surface.harness, "scope": sr.surface.scope,
            "path": sr.surface.relative_path,
            "classification": sr.classification, "drift": sr.drift,
            "persona_fold": sr.persona_fold, "committed": sr.path in committed,
            "expected_sha256": sr.expected_sha256,
            "actual_sha256": sr.actual_sha256}


def run_witness_payload(report: ReconcileReport, *, run_ord: int,
                        pool_digest: str) -> dict:
    """The run's witness record: what the loop decided, bound to the pool it
    read. Path-clean throughout (no absolute host path escapes), so it is a
    portable, re-derivable receipt, fired once per run even an all-clean one."""
    committed = frozenset(report.committed)
    return {"kind": WITNESS_KIND, "run_ord": run_ord,
            "pool_digest": pool_digest, "ok": report.ok,
            "surfaces": [_witness_row(sr, committed) for sr in report.surfaces]}


def reconcile_exit_code(report: ReconcileReport) -> int:
    """0 for a clean run, 1 when any surface still needs a human or refused."""
    return 0 if report.ok else 1
