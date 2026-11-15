"""drift.py -- V2: the rendered-surface drift check.

A managed surface's region interior is a pure function of the record pool. R1's
render composition (render_surface over pool_for) has no clock and no
randomness, so re-deriving a surface from the pool is byte-stable. This band
re-derives each catalog surface, compares the derived interior to what is on
disk, and returns a sha256-keyed verdict per surface. It reads; it never writes.

It scores canon-owned bytes: the region interior between the markers, not the
whole host file. The prefix and suffix are hand-authored and preserved by
construction, so a change there is the host's own prose, never canon drift. A
change inside the region is drift; a CRLF line ending is not. A reserved block
the region carries (the resume brief `canon switch` writes) is part of the
expected render, since no record in the pool renders it.

Total, like the fidelity gate: every refusal (a deformed marker, a mis-scoped
region, a render the pool cannot represent) is returned as a verdict, never
raised. drift_exit_code maps a report to a process status so a caller can gate a
build on it.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from canon.layering import LayeringError
from canon.region import RegionError, extract_region
from canon.registry import (
    SURFACE_CATALOG,
    Surface,
    pool_for,
    resolve_surface_path,
)
from canon.schema import Record
from canon.surface import carried_blocks, render_surface
from canon.textblock import RenderRefused

VERDICT_MATCH = "match"
VERDICT_DRIFT = "drift"
VERDICT_OFF_LIMITS = "off-limits"
VERDICT_REFUSED = "refused"
VERDICT_MISSING = "missing"

# The verdicts that keep a report clean: the surface is faithful, or it is not
# canon's to write (no region, or an absent file). A drift or a refusal fails.
_OK_VERDICTS = frozenset({VERDICT_MATCH, VERDICT_OFF_LIMITS, VERDICT_MISSING})


@dataclass(frozen=True, slots=True)
class SurfaceDrift:
    """One surface's drift verdict. The two sha256 fields are set for a match or
    a drift, the cases where both interiors exist; reason carries the refusal
    text for the others."""

    surface: Surface
    path: str
    verdict: str
    expected_sha256: str | None
    actual_sha256: str | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class DriftReport:
    """The whole-catalog verdict. ok is true only when no surface drifted and
    none refused."""

    ok: bool
    surfaces: tuple[SurfaceDrift, ...]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def surface_drift(surface: Surface, pool: list[Record], *, home: str,
                  workspace: str, read_text) -> SurfaceDrift:
    """Re-derive `surface` from `pool` and compare it to the on-disk region
    interior, returning a sha256-keyed verdict.

    Read-only and total: read_text returns None for an absent file, and every
    refusal (a deformed marker, a mis-scoped region, an unrepresentable render)
    is a verdict rather than an exception.
    """
    path = resolve_surface_path(surface, home=home, workspace=workspace)
    host = read_text(path)
    if host is None:
        return SurfaceDrift(surface, path, VERDICT_MISSING, None, None,
                            "surface file is absent")
    try:
        region = extract_region(host)
    except RegionError as exc:
        return SurfaceDrift(surface, path, VERDICT_REFUSED, None, None,
                            f"deformed region: {exc}")
    if not region.present:
        return SurfaceDrift(surface, path, VERDICT_OFF_LIMITS, None, None,
                            "host has no canon region")
    if region.scope != surface.scope:
        return SurfaceDrift(
            surface, path, VERDICT_REFUSED, None, None,
            f"region scope {region.scope!r} != surface scope {surface.scope!r}")
    try:
        expected = render_surface(pool_for(surface, pool) + carried_blocks(host),
                                  surface.scope)
    except LayeringError as exc:
        # A pool that carries a non-personality-block record, or a record with
        # an unknown scope, is not a personality set layering can place. D-58:
        # surface_drift folds that raise into a verdict so the totality
        # guarantee holds for a realistic mixed pool a caller supplies.
        return SurfaceDrift(surface, path, VERDICT_REFUSED, None, None,
                            f"layering refused: {exc}")
    except RenderRefused as exc:
        return SurfaceDrift(surface, path, VERDICT_REFUSED, None, None,
                            f"render refused: {exc}")
    actual = region.inner.replace("\r\n", "\n")
    expected_sha, actual_sha = _sha256(expected), _sha256(actual)
    verdict = VERDICT_MATCH if expected == actual else VERDICT_DRIFT
    return SurfaceDrift(surface, path, verdict, expected_sha, actual_sha, None)


def drift_report(pool: list[Record], *, home: str, workspace: str, read_text,
                 surfaces: tuple[Surface, ...] | None = None) -> DriftReport:
    """Drift-check every surface in `surfaces`, defaulting to the whole catalog.
    The catalog is the manifest of which blocks render to which file, so V2
    needs no separate manifest artifact."""
    chosen = SURFACE_CATALOG if surfaces is None else surfaces
    results = tuple(
        surface_drift(s, pool, home=home, workspace=workspace,
                      read_text=read_text)
        for s in chosen)
    ok = all(r.verdict in _OK_VERDICTS for r in results)
    return DriftReport(ok=ok, surfaces=results)


def drift_exit_code(report: DriftReport) -> int:
    """0 for a clean report, 1 when any surface drifted or refused."""
    return 0 if report.ok else 1
