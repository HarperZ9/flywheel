"""canon_check.py -- M4.4 optional composition. One aggregate verdict over
the four verdict-returning check legs canon ships: drift (V2), vault
round-trip (R2 fidelity), vault symmetric round-trip (M4.2 fidelity), and
persona basis (V3). The composition adds no new schema, no new capability,
and no new refusal type; it aggregates existing verdicts and folds their
`ok` bits into one gate a build keys on (D-100).

Each leg opts in via its injected seam. A leg whose seam is not wired reports
None and does not affect `ok`. The composition is read-only: no leg here
mutates state on disk or in memory. `reconcile` is not a leg because it is
an action (writes host files, raises durable gates); a caller who wants a
run-and-check composes `reconcile` separately.

canon_check itself never raises. Every leg is documented total; a wiring
fault a leg raises (a bad assessor return shape, for instance) propagates
out to the caller, matching the fail-loud discipline in D-38 / D-39 rather
than swallowing the wiring bug.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from canon.drift import DriftReport, drift_report
from canon.persona_thesis import (
    MATCH,
    DriftVerdict,
    assess_persona,
)
from canon.schema import KIND_SYNTHESIZED_PERSONA_L3, Record
from canon.vault_fidelity import VaultVerdict, vault_roundtrip_report
from canon.vault_read_fidelity import VaultReadVerdict, vault_symmetric_report


@dataclass(frozen=True, slots=True)
class CanonCheckReport:
    """Aggregate verdict over the four canon check legs.

    A leg with its seam wired runs and its report lands in the matching
    field. A leg without its seam wired reports None and does not affect
    `ok`. `ok` is True iff every wired leg's own `ok` reads True. `reasons`
    carries a short label per failed leg; a persona failure names the
    verdict (`persona:DRIFT`, `persona:UNVERIFIABLE`) so a caller reading
    the reasons alone can tell the fail class. `exit_code` is 0 iff `ok`.
    """

    drift: DriftReport | None
    vault: VaultVerdict | None
    vault_symmetric: VaultReadVerdict | None
    persona: tuple[DriftVerdict, ...] | None
    ok: bool
    reasons: tuple[str, ...]
    exit_code: int


def _persona_ok(verdict: DriftVerdict) -> bool:
    """A persona leg passes iff its verdict is MATCH. DRIFT is a proven
    erosion (D-46); UNVERIFIABLE is an honest null that fails the aggregate
    closed (a caller who wants a checked build wires a real assessor)."""
    return verdict.verdict == MATCH


def canon_check(
    pool: list[Record],
    *,
    home: str | None = None,
    workspace: str | None = None,
    read_text: Callable[[str], str | None] | None = None,
    assess: Callable[[dict], list] | None = None,
) -> CanonCheckReport:
    """Run every check leg whose seam is wired and fold the results into one
    aggregate verdict.

    - drift runs iff `home`, `workspace`, and `read_text` are all supplied.
    - vault runs unconditionally (pool-only).
    - vault_symmetric runs unconditionally (pool-only).
    - persona runs iff `assess` is supplied; every
      `synthesized-persona-l3` record in the pool is assessed against the
      pool, and the tuple of verdicts lands in `persona` (empty tuple if the
      pool has no persona records).

    Every underlying leg is total; this composition raises nothing on hostile
    input the legs already handle.
    """
    drift_r = _run_drift(pool, home, workspace, read_text)
    vault_v = vault_roundtrip_report(pool)
    vault_sym = vault_symmetric_report(pool)
    persona_v = _run_persona(pool, assess)

    reasons = _collect_reasons(drift_r, vault_v, vault_sym, persona_v)
    ok = not reasons
    return CanonCheckReport(
        drift=drift_r,
        vault=vault_v,
        vault_symmetric=vault_sym,
        persona=persona_v,
        ok=ok,
        reasons=tuple(reasons),
        exit_code=0 if ok else 1,
    )


def _run_drift(pool, home, workspace, read_text) -> DriftReport | None:
    if home is None or workspace is None or read_text is None:
        return None
    return drift_report(
        pool, home=home, workspace=workspace, read_text=read_text)


def _run_persona(pool, assess) -> tuple[DriftVerdict, ...] | None:
    if assess is None:
        return None
    return tuple(
        assess_persona(rec, pool=pool, assess=assess)
        for rec in pool
        if rec.kind == KIND_SYNTHESIZED_PERSONA_L3
    )


def _collect_reasons(drift_r, vault_v, vault_sym, persona_v) -> list[str]:
    reasons: list[str] = []
    if drift_r is not None and not drift_r.ok:
        reasons.append("drift")
    if not vault_v.ok:
        reasons.append("vault")
    if not vault_sym.ok:
        reasons.append("vault_symmetric")
    if persona_v is not None:
        for v in persona_v:
            if not _persona_ok(v):
                reasons.append(f"persona:{v.verdict}")
    return reasons


def canon_check_exit_code(report: CanonCheckReport) -> int:
    """0 iff every wired leg passed, 1 otherwise. Signature and semantics
    mirror `drift_exit_code` and `reconcile_exit_code`, so a build that
    already keys on those two total gates picks up the aggregate with no
    bespoke wiring."""
    return report.exit_code
