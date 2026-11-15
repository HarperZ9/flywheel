"""test_vault_reader_fidelity.py -- M4.2: the symmetric round-trip verdict.

R2's vault_fidelity certifies render_note<->ingest_note is lossless on the
single-note codec. This module extends that guarantee to the WHOLE VAULT round
trip: plan_vault writes a pool into a FakeFS, read_vault reads it back, and
pool_out is field-diffed against pool_in with the same classify_note_losses R2
uses.

The declared-drop vocabulary is EMPTY (D-83, symmetric to
DECLARED_NOTE_DROPS). A codec regression that dropped a field would raise a
NoteLoss and fail the verdict closed here as well.
"""
from __future__ import annotations

from dataclasses import replace

from canon.schema import Temporal
from canon.vault_read_fidelity import (
    DECLARED_READ_DROPS,
    FakeFS,
    VaultReadVerdict,
    vault_symmetric_report,
)

from ._helpers import RECORD_FILES, load_record


def test_symmetric_report_all_five_kinds_zero_loss():
    records = [load_record(p) for p in RECORD_FILES.values()]
    v = vault_symmetric_report(records)
    assert isinstance(v, VaultReadVerdict)
    assert v.write_ok is True
    assert v.read_ok is True
    assert v.pool_matches is True
    assert v.losses == ()
    assert v.refusals == ()
    assert v.ok is True
    assert v.n_records_in == 5
    assert v.n_records_out == 5


def test_declared_read_drops_is_empty():
    assert DECLARED_READ_DROPS == frozenset()
    v = vault_symmetric_report([load_record(RECORD_FILES["personality-block"])])
    assert v.declared_drops == frozenset()


def test_symmetric_report_kleene_star_idempotence():
    """A record read back and re-written renders byte-identical the second
    time (R2 renders are clock-free)."""
    records = [load_record(p) for p in RECORD_FILES.values()]
    v1 = vault_symmetric_report(records)
    assert v1.ok
    v2 = vault_symmetric_report(list(v1.read_result.pool))
    assert v2.ok
    assert v2.n_records_out == v1.n_records_out


def test_symmetric_report_catches_write_leg_refusal_no_raise():
    # A research-artifact-ref that carries a temporal block: render refuses
    # it and plan_vault aborts the whole plan.
    good = load_record(RECORD_FILES["personality-block"])
    bad = load_record(RECORD_FILES["research-artifact-ref"]).with_temporal(
        Temporal(supersedes="x"))
    v = vault_symmetric_report([good, bad])
    assert v.ok is False
    assert v.write_ok is False
    assert v.read_ok is False
    assert v.n_records_in == 2
    assert any(r.where == "write" for r in v.refusals)


def test_symmetric_report_catches_mutation_as_undeclared(monkeypatch):
    """A read leg that silently mutated a field would appear as UNDECLARED
    loss and fail closed."""
    import canon.vault_read_fidelity as vrf

    real_read = vrf.read_vault

    def lossy(root, *, list_dir, read_text):
        result = real_read(root, list_dir=list_dir, read_text=read_text)
        mutated = tuple(replace(r, data={**(r.data if isinstance(r.data, dict) else {}),
                                        "body": "MUTATED-BY-TEST"})
                        if r.kind == "personality-block" else r
                        for r in result.pool)
        return replace(result, pool=mutated)

    monkeypatch.setattr(vrf, "read_vault", lossy)
    records = [load_record(RECORD_FILES["personality-block"])]
    v = vault_symmetric_report(records)
    assert v.ok is False
    assert any(l.kind == "UNDECLARED" for l in v.losses)


def test_fake_fs_returns_none_on_absent_read():
    fs = FakeFS()
    assert fs.read_text("/nonexistent/path.md") is None


def test_fake_fs_lists_only_under_root():
    fs = FakeFS()
    fs.write_text("/root/a.md", "a")
    fs.write_text("/other/b.md", "b")
    listed = fs.list_dir("/root")
    assert "a.md" in listed
    assert "b.md" not in listed
