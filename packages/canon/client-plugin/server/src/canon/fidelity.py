"""fidelity.py -- the R0 go/no-go artifact.

roundtrip_report renders a scope-homogeneous block set into the region interior,
ingests it back, and returns a FidelityVerdict answering four questions: did the
set round-trip to its canonical form (round_trip_ok), is the render a fixed point
(idempotent), are the bytes outside the markers preserved across the host
encoding matrix (outside_preserved), and is every field the text leg drops an
accounted-for declared drop rather than a silent loss. `ok` is the conjunction.

The drop ledger does not certify itself. classify_losses enumerates every Record
field structurally (dataclasses.fields over Provenance and Temporal, plus the
carried top-level fields) and diffs `got` against the RAW input -- never against
canonicalize_record, which would let a renderer and its own reference agree on a
mistake. A changed field outside the declared-drop vocabulary is an UNDECLARED
loss and fails the gate closed. The vocabulary reconciles against the backend
capability tokens: the six foreign-provenance fields map to CAP_FOREIGN_PROVENANCE
and temporal.valid_until to CAP_TEMPORAL. A zero-drop store (SqliteBackend)
witnesses, in the tests, that the raw input is itself faithfully storable, so the
"before" the ledger diffs against is grounded, not assumed.

Every refusal on either leg (render, extract, ingest) is caught and returned as a
Refusal with ok=False; the verdict never propagates an exception.
"""
from __future__ import annotations

from dataclasses import dataclass, fields

from canon.backends.base import CAP_FOREIGN_PROVENANCE, CAP_TEMPORAL
from canon.region import RegionError, extract_region, splice_region
from canon.schema import Provenance, Record, Temporal
from canon.textblock import (
    IngestRefused,
    RenderRefused,
    canonicalize_record,
    ingest_region,
    render_region,
)

# ---- the declared-drop vocabulary, bound to capability tokens -----------------

DROP_TO_CAP = {
    "provenance.harness": CAP_FOREIGN_PROVENANCE,
    "provenance.source_hash": CAP_FOREIGN_PROVENANCE,
    "provenance.native_id": CAP_FOREIGN_PROVENANCE,
    "provenance.session_id": CAP_FOREIGN_PROVENANCE,
    "provenance.create_time": CAP_FOREIGN_PROVENANCE,
    "provenance.model_slug": CAP_FOREIGN_PROVENANCE,
    "temporal.valid_until": CAP_TEMPORAL,
}
DECLARED_FIELD_DROPS = frozenset(DROP_TO_CAP)

_PROV_FIELDS = tuple(f.name for f in fields(Provenance))
_TEMP_FIELDS = tuple(f.name for f in fields(Temporal))
_EMPTY_TEMPORAL = Temporal(valid_until=None, supersedes=None)
_CARRIED_TOP = ("kind", "id", "scope", "data")


# ---- verdict shapes -----------------------------------------------------------

@dataclass(frozen=True, slots=True)
class FieldLoss:
    """One field where the round-tripped record differs from the raw input.
    kind is DECLARED (an accounted-for text-leg drop) or UNDECLARED (a change on
    a field the text surface is meant to carry -- a fail-closed condition)."""

    record_id: str
    field: str
    kind: str
    before: object
    after: object
    reason: str


@dataclass(frozen=True, slots=True)
class Refusal:
    """A leg of the round trip refused loudly. `where` is render, extract, or
    ingest; the report returns this instead of propagating the exception."""

    record_id: str | None
    where: str
    reason: str


@dataclass(frozen=True, slots=True)
class FidelityVerdict:
    """The go/no-go result. ok is the conjunction of round_trip_ok, idempotent,
    outside_preserved, and the absence of any UNDECLARED loss."""

    ok: bool
    round_trip_ok: bool
    outside_preserved: bool
    idempotent: bool
    declared_drops: frozenset
    losses: tuple
    refusals: tuple
    scope: str
    n_records: int


# ---- the structural drop ledger (diffs GOT against RAW input) -----------------

def classify_losses(raw: Record, got: Record) -> list[FieldLoss]:
    """Every field where `got` differs from the RAW input `raw`, classified as a
    DECLARED text-leg drop or an UNDECLARED loss. Enumerates the Provenance and
    Temporal fields with dataclasses.fields so a field added to the schema cannot
    slip past the ledger unlisted, and diffs against `raw` (not canonicalize) so
    the ledger cannot certify a renderer that agrees with its own reference."""
    losses: list[FieldLoss] = []
    rid = raw.id
    for name in _CARRIED_TOP:
        _diff_field(rid, name, getattr(raw, name), getattr(got, name), losses)
    _diff_sub(rid, "provenance", raw.provenance, got.provenance,
              _PROV_FIELDS, losses)
    _diff_sub(rid, "temporal", raw.temporal or _EMPTY_TEMPORAL,
              got.temporal or _EMPTY_TEMPORAL, _TEMP_FIELDS, losses)
    return losses


def _diff_sub(rid, prefix, rawobj, gotobj, names, losses) -> None:
    for name in names:
        _diff_field(rid, f"{prefix}.{name}",
                    getattr(rawobj, name), getattr(gotobj, name), losses)


def _diff_field(rid, path, before, after, losses) -> None:
    if before == after:
        return
    declared = path in DECLARED_FIELD_DROPS
    losses.append(FieldLoss(
        rid, path, "DECLARED" if declared else "UNDECLARED", before, after,
        "declared text-leg drop" if declared
        else "undeclared change on a carried field"))


# ---- the host encoding matrix (outside-bytes preservation) --------------------

def _host_fixture(term: str, *, bom: str = "", trailing: bool = True) -> bytes:
    lines = [
        f"{bom}intro prose",
        "<!-- canon:begin scope=workspace -->",
        '<!-- canon:block id="x" -->',
        "## X",
        "body",
        "<!-- canon:end -->",
        "outro",
    ]
    text = term.join(lines) + (term if trailing else "")
    return text.encode("utf-8")


_HOST_FIXTURES = (
    _host_fixture("\n"),                 # LF
    _host_fixture("\r\n"),               # CRLF host
    _host_fixture("\n", bom="﻿"),   # leading BOM
    _host_fixture("\n", trailing=False),  # no trailing newline
)


def _host_matrix_ok(file_text: str | None = None) -> bool:
    """True iff extract/splice preserve every byte outside the markers across the
    LF / CRLF / BOM / no-trailing-newline host matrix, and (when a target file is
    given) that file carries a writable region. Computed, never assumed: the
    verdict reads outside_preserved straight from this."""
    for raw in _HOST_FIXTURES:
        h = raw.decode("utf-8")
        s = extract_region(h)
        if not s.present:
            return False
        if splice_region(h, s.inner).encode("utf-8") != raw:
            return False
        out = splice_region(h, "REWRITTEN\n")
        if not (out.startswith(s.prefix) and out.endswith(s.suffix)):
            return False
    if file_text is not None:
        try:
            if not extract_region(file_text).present:
                return False
        except RegionError:
            return False
    return True


# ---- the go/no-go report ------------------------------------------------------

def roundtrip_report(records: list[Record], scope: str, *,
                     file_text: str | None = None) -> FidelityVerdict:
    """Render `records` into the region interior, ingest them back, and report
    fidelity. Refusals on any leg are caught and returned (ok=False), never
    raised. Pass file_text to also require a writable region in a real host."""
    outside = _host_matrix_ok(file_text)
    try:
        text = render_region(records, scope)
    except RenderRefused as e:
        return _fail(scope, len(records), outside,
                     [Refusal(e.record_id, "render", e.reason)])
    synth = f"<!-- canon:begin scope={scope} -->\n{text}<!-- canon:end -->\n"
    try:
        got = ingest_region(synth)
    except RegionError as e:
        return _fail(scope, len(records), outside,
                     [Refusal(None, "extract", str(e))])
    except IngestRefused as e:
        return _fail(scope, len(records), outside,
                     [Refusal(None, "ingest", e.reason)])
    expected = {(r.scope, r.id): canonicalize_record(r) for r in records}
    got_map = {(g.scope, g.id): g for g in got}
    round_trip_ok = (set(expected) == set(got_map)
                     and all(expected[k] == got_map[k] for k in expected))
    losses = _collect_losses(records, got_map)
    try:
        idempotent = render_region(got, scope) == text
    except RenderRefused:
        idempotent = False
    undeclared = any(l.kind == "UNDECLARED" for l in losses)
    ok = round_trip_ok and idempotent and outside and not undeclared
    return FidelityVerdict(
        ok=ok, round_trip_ok=round_trip_ok, outside_preserved=outside,
        idempotent=idempotent, declared_drops=DECLARED_FIELD_DROPS,
        losses=tuple(losses), refusals=(), scope=scope, n_records=len(records))


def _collect_losses(records, got_map) -> list[FieldLoss]:
    losses: list[FieldLoss] = []
    for r in records:
        g = got_map.get((r.scope, r.id))
        if g is not None:
            losses.extend(classify_losses(r, g))
    return losses


def _fail(scope, n, outside, refusals) -> FidelityVerdict:
    return FidelityVerdict(
        ok=False, round_trip_ok=False, outside_preserved=outside,
        idempotent=False, declared_drops=DECLARED_FIELD_DROPS,
        losses=(), refusals=tuple(refusals), scope=scope, n_records=n)
