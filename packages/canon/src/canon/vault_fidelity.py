"""vault_fidelity.py -- R2: the vault round-trip verdict.

The R0 fidelity gate certifies a LOSSY text projection against a declared-drop
ledger bound to backend capability tokens. The vault note codec is different in
kind: its frontmatter `canon:` key carries `record.to_json()` verbatim, so the
`render_note -> ingest_note` round trip is lossless. The declared-drop vocabulary
is therefore EMPTY -- every field must return byte-identical, and any field that
differs is an UNDECLARED loss that fails the verdict closed.

classify_note_losses enumerates every Record field structurally: dataclasses.fields
over Record gives the top-level fields (`_CARRIED_TOP`, the two sub-records
excluded), and dataclasses.fields over Provenance and Temporal gives their
sub-fields. It diffs `got` against the RAW input -- never a canonicalized form --
so a codec regression that drops or mangles a field cannot certify itself. A field
added to the schema at any level is enumerated automatically, so it cannot slip
past the ledger unlisted.

There is no host-encoding leg here (R0's outside-byte preservation): a note is a
whole file, not a region spliced into foreign bytes, so there are no outside
bytes to conserve. Every leg refusal (render, ingest) is caught and returned as a
Refusal with ok=False; the report never propagates an exception.
"""
from __future__ import annotations

from dataclasses import dataclass, fields

# The refusal shape is shared with the R0 gate: same (record_id, where, reason)
# meaning, so the two fidelity artifacts speak one vocabulary.
from canon.fidelity import Refusal
from canon.schema import Provenance, Record, Temporal
from canon.vault import NoteRefused, VaultError, ingest_note, render_note

_PROV_FIELDS = tuple(f.name for f in fields(Provenance))
_TEMP_FIELDS = tuple(f.name for f in fields(Temporal))
_EMPTY_TEMPORAL = Temporal(valid_until=None, supersedes=None)
# The top-level Record fields diffed directly, derived from the schema so a field
# added there is covered without a hand edit. provenance and temporal are the two
# sub-records, diffed field-by-field via _diff_sub, so they are excluded here.
_SUBRECORD_TOP = ("provenance", "temporal")
_CARRIED_TOP = tuple(f.name for f in fields(Record) if f.name not in _SUBRECORD_TOP)

# The note carrier is lossless: there is no accounted-for drop, so every field
# difference is undeclared. Named so the verdict can report the empty ledger.
DECLARED_NOTE_DROPS: frozenset = frozenset()


@dataclass(frozen=True, slots=True)
class NoteLoss:
    """One field where the round-tripped record differs from the RAW input. The
    vault codec is lossless, so `kind` is always UNDECLARED -- a fail-closed
    condition -- and the presence of any NoteLoss fails the verdict."""

    record_id: str
    field: str
    kind: str
    before: object
    after: object
    reason: str


@dataclass(frozen=True, slots=True)
class VaultVerdict:
    """The vault round-trip result. ok is the conjunction of round_trip_ok,
    idempotent, and the absence of any loss or refusal. declared_drops is empty:
    the note carrier is lossless, so nothing is an accounted-for drop."""

    ok: bool
    round_trip_ok: bool
    idempotent: bool
    declared_drops: frozenset
    losses: tuple
    refusals: tuple
    n_records: int


def classify_note_losses(raw: Record, got: Record) -> list[NoteLoss]:
    """Every field where `got` differs from the RAW input `raw`. Enumerates the
    top-level and the Provenance/Temporal sub-fields with dataclasses.fields so a
    new schema field cannot slip past unlisted, and diffs against `raw` (not a
    canonical form) so a codec regression cannot certify itself. The vault is
    lossless, so every difference is UNDECLARED."""
    losses: list[NoteLoss] = []
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
    losses.append(NoteLoss(
        rid, path, "UNDECLARED", before, after,
        "undeclared change on a losslessly carried field"))


def vault_roundtrip_report(records: list[Record]) -> VaultVerdict:
    """Render each record to its note, ingest it back, and report fidelity.

    Refusals on either leg (render, ingest) are caught and returned (ok=False),
    never raised. Because the note carrier is lossless, a faithful pool returns
    zero losses; any field difference is an UNDECLARED loss and fails closed.
    """
    refusals: list[Refusal] = []
    pairs: list[tuple[Record, Record, str]] = []
    for record in records:
        try:
            note = render_note(record)
        except NoteRefused as exc:
            refusals.append(Refusal(record.id, "render", str(exc)))
            continue
        try:
            got = ingest_note(note)
        except VaultError as exc:
            refusals.append(Refusal(record.id, "ingest", str(exc)))
            continue
        pairs.append((record, got, note))

    losses: list[NoteLoss] = []
    round_trip_ok = not refusals
    idempotent = True
    for raw, got, note in pairs:
        losses.extend(classify_note_losses(raw, got))
        if got != raw:
            round_trip_ok = False
        try:
            if render_note(got) != note:
                idempotent = False
        except NoteRefused:
            idempotent = False

    undeclared = any(l.kind == "UNDECLARED" for l in losses)
    ok = round_trip_ok and idempotent and not undeclared and not refusals
    return VaultVerdict(
        ok=ok, round_trip_ok=round_trip_ok, idempotent=idempotent,
        declared_drops=DECLARED_NOTE_DROPS, losses=tuple(losses),
        refusals=tuple(refusals), n_records=len(records))
