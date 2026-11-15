"""test_vault_fidelity.py -- R2 Module 4: the vault round-trip verdict.

The R0 fidelity gate certifies a lossy text projection against a declared-drop
ledger. The vault note codec is different in kind: its `canon:` key carries
`record.to_json()` verbatim, so the round trip is lossless and the declared-drop
vocabulary is EMPTY. Every field must return byte-identical; any field that
differs is an UNDECLARED loss and fails the verdict closed. Like the R0 gate, the
report never propagates an exception -- a render or ingest refusal is caught and
returned as a refusal with ok=False.
"""
from __future__ import annotations

from dataclasses import replace

from canon.schema import Temporal
from canon.vault_fidelity import (
    NoteLoss,
    VaultVerdict,
    classify_note_losses,
    vault_roundtrip_report,
)

from ._helpers import RECORD_FILES, load_record


# 35
def test_vault_roundtrip_report_all_kinds_zero_loss():
    records = [load_record(p) for p in RECORD_FILES.values()]
    v = vault_roundtrip_report(records)
    assert isinstance(v, VaultVerdict)
    assert v.ok
    assert v.round_trip_ok and v.idempotent
    assert v.losses == ()
    assert v.refusals == ()
    assert v.declared_drops == frozenset()  # the vault is lossless: no drops
    assert v.n_records == 5


# 36
def test_vault_roundtrip_report_fails_closed_on_undeclared_loss(monkeypatch):
    import canon.vault_fidelity as vf

    raw = load_record(RECORD_FILES["personality-block"])

    # A direct unit on the classifier: a mutated `got` is an undeclared loss.
    got = replace(raw, data={**raw.data, "body": "MUTATED"})
    losses = classify_note_losses(raw, got)
    assert any(isinstance(l, NoteLoss) and l.kind == "UNDECLARED"
               and l.field == "data" for l in losses)

    # A lossy ingest (simulating a codec regression) fails the verdict closed.
    real = vf.ingest_note

    def lossy(note):
        rec = real(note)
        return replace(rec, data={**rec.data, "body": "DROPPED-BY-LOSSY-CODEC"})

    monkeypatch.setattr(vf, "ingest_note", lossy)
    v = vault_roundtrip_report([raw])
    assert not v.ok
    assert not v.round_trip_ok
    assert any(l.kind == "UNDECLARED" for l in v.losses)


# 37
def test_vault_roundtrip_report_catches_refusal_no_raise():
    good = load_record(RECORD_FILES["personality-block"])
    # a research-artifact-ref carrying a temporal block: render refuses it.
    bad = load_record(RECORD_FILES["research-artifact-ref"]).with_temporal(
        Temporal(supersedes="x"))
    v = vault_roundtrip_report([good, bad])
    assert not v.ok
    assert any(r.where == "render" and r.record_id == bad.id for r in v.refusals)
    # the report processed the whole pool without raising
    assert v.n_records == 2


# 38 -- Root E: the module claims a new schema field is enumerated automatically
# and cannot slip past the ledger unlisted. That holds only if the diff covers
# every Record field. Lock it: the directly-diffed top-level fields plus the two
# sub-record fields are exactly the Record fields, and the sub-records are not
# also diffed as flat scalars (which would double-count and misreport them).
def test_carried_fields_cover_every_record_field():
    from dataclasses import fields

    from canon.schema import Record
    import canon.vault_fidelity as vf

    all_fields = {f.name for f in fields(Record)}
    assert set(vf._CARRIED_TOP) | {"provenance", "temporal"} == all_fields
    assert "provenance" not in vf._CARRIED_TOP
    assert "temporal" not in vf._CARRIED_TOP
