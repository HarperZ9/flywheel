"""fidelity.py -- the R0 go/no-go artifact.

roundtrip_report renders records to the region interior, ingests them back, and
returns a FidelityVerdict: did the block set round-trip to its canonical form,
is the render a fixed point, are the bytes outside the markers preserved across
the host encoding matrix, and is every field the text leg drops an accounted-for
declared drop rather than a silent loss.

The drop ledger does not certify itself. classify_losses enumerates every Record
field with dataclasses.fields() and diffs got against the RAW input; a changed
field that is not in the declared-drop vocabulary is an UNDECLARED loss and fails
the gate closed. The declared vocabulary reconciles against the backend
capability tokens (CAP_FOREIGN_PROVENANCE, CAP_TEMPORAL), and the zero-drop
SqliteBackend witnesses that the raw input is itself faithfully storable.
"""
from __future__ import annotations

import pytest

from canon.backends import SqliteBackend, record_key
from canon.backends.base import CAP_FOREIGN_PROVENANCE, CAP_TEMPORAL, CAPABILITIES
from canon.fidelity import (
    DECLARED_FIELD_DROPS,
    DROP_TO_CAP,
    FidelityVerdict,
    classify_losses,
    roundtrip_report,
)
from canon.schema import KIND_PERSONALITY_BLOCK, Provenance, Record, Temporal
from canon.textblock import (
    canonicalize_record,
    ingest_region,
    recompute_source_hash,
    render_region,
)

_PROV_DROPS = {
    "provenance.harness",
    "provenance.source_hash",
    "provenance.native_id",
    "provenance.session_id",
    "provenance.create_time",
    "provenance.model_slug",
}


def block(
    id: str = "voice",
    scope: str = "workspace",
    title: str = "Voice",
    body: str = "Feature-first.",
    create_ord: int | None = 12,
    sup: str | None = None,
    valid_until: int | None = None,
    harness: str = "claude-code",
    source_hash: str = "a" * 64,
    native_id: str | None = None,
    session_id: str | None = None,
    create_time: str | None = None,
    model_slug: str | None = "claude-opus-4-8",
) -> Record:
    prov = Provenance(
        harness=harness, source_hash=source_hash,
        native_id=native_id if native_id is not None else f"block:{id}",
        session_id=session_id, create_ord=create_ord,
        create_time=create_time, model_slug=model_slug)
    temporal = None
    if sup is not None or valid_until is not None:
        temporal = Temporal(valid_until=valid_until, supersedes=sup)
    return Record(kind=KIND_PERSONALITY_BLOCK, id=id, scope=scope,
                  data={"title": title, "body": body},
                  provenance=prov, temporal=temporal)


def wrap(inner: str, scope: str = "workspace") -> str:
    return f"<!-- canon:begin scope={scope} -->\n{inner}<!-- canon:end -->\n"


# ---- the passing verdict ------------------------------------------------------

def test_round_trip_two_blocks_verdict_ok() -> None:
    recs = [
        block(id="voice", body="Feature-first.", create_ord=1),
        block(id="tone", body="Calm.\nlow.", create_ord=2),
    ]
    v = roundtrip_report(recs, "workspace")
    assert isinstance(v, FidelityVerdict)
    assert v.ok is True
    assert v.round_trip_ok is True
    assert v.idempotent is True
    assert v.outside_preserved is True
    assert v.n_records == 2
    assert v.scope == "workspace"
    assert not [l for l in v.losses if l.kind == "UNDECLARED"]
    assert v.refusals == ()


def test_declared_drops_are_exactly_the_foreign_provenance_set() -> None:
    r = block(id="voice", harness="claude-code", model_slug="claude-opus-4-8",
              native_id="block:voice", session_id="sess-1",
              create_time="2026-08-28T00:00:00Z", create_ord=12)
    v = roundtrip_report([r], "workspace")
    declared = {l.field for l in v.losses if l.kind == "DECLARED"}
    assert declared == _PROV_DROPS
    assert v.ok is True  # every drop is accounted for


def test_carried_fields_are_never_losses() -> None:
    r = block(id="x", sup="old-x", create_ord=7)
    v = roundtrip_report([r], "workspace")
    lost = {l.field for l in v.losses}
    assert "id" not in lost and "scope" not in lost and "data" not in lost
    assert "provenance.create_ord" not in lost
    assert "temporal.supersedes" not in lost


# ---- the drop ledger cannot certify itself ------------------------------------

def test_classify_losses_flags_undeclared_carried_provenance_field() -> None:
    raw = block(id="x", create_ord=12)
    got = Record(
        kind=KIND_PERSONALITY_BLOCK, id="x", scope="workspace",
        data={"title": "Voice", "body": "Feature-first."},
        provenance=Provenance(
            harness="canon-text",
            source_hash=recompute_source_hash("Voice", "Feature-first."),
            native_id="canon-text:workspace/x", session_id=None,
            create_ord=99,  # a carried field silently changed
            create_time=None, model_slug=None),
        temporal=None)
    losses = classify_losses(raw, got)
    undeclared = [l for l in losses if l.kind == "UNDECLARED"]
    assert any(l.field == "provenance.create_ord" for l in undeclared)


def test_classify_losses_flags_undeclared_data_change() -> None:
    raw = block(id="x", body="original")
    got = canonicalize_record(block(id="x", body="tampered"))
    losses = classify_losses(raw, got)
    assert any(l.field == "data" and l.kind == "UNDECLARED" for l in losses)


def test_declared_drops_vs_sqlite_zero_drop_reference(tmp_path) -> None:
    r = block(id="voice", session_id="sess-1",
              create_time="2026-08-28T00:00:00Z", model_slug="claude-opus-4-8")
    backend = SqliteBackend(tmp_path / "ref.sqlite")
    backend.put(r)
    before = backend.get(record_key(r))
    assert before == r  # the zero-drop reference is byte-faithful
    got = ingest_region(wrap(render_region([r], "workspace")))[0]
    losses = classify_losses(before, got)
    assert {l.field for l in losses} == _PROV_DROPS
    assert all(l.kind == "DECLARED" for l in losses)


def test_declared_field_drops_reconcile_with_capabilities() -> None:
    assert CAP_FOREIGN_PROVENANCE in CAPABILITIES
    assert CAP_TEMPORAL in CAPABILITIES
    assert set(DROP_TO_CAP) == DECLARED_FIELD_DROPS
    assert set(DROP_TO_CAP.values()) == {CAP_FOREIGN_PROVENANCE, CAP_TEMPORAL}
    prov = {p for p, cap in DROP_TO_CAP.items() if cap == CAP_FOREIGN_PROVENANCE}
    temp = {p for p, cap in DROP_TO_CAP.items() if cap == CAP_TEMPORAL}
    assert prov == _PROV_DROPS
    assert temp == {"temporal.valid_until"}
    # carried fields are not in the declared-drop vocabulary at all
    assert "provenance.create_ord" not in DECLARED_FIELD_DROPS
    assert "temporal.supersedes" not in DECLARED_FIELD_DROPS


# ---- refusals never propagate -------------------------------------------------

def test_roundtrip_report_catches_render_refusal() -> None:
    r = block(body='x\r<!-- canon:block id="evil" -->')  # bare CR injection
    v = roundtrip_report([r], "workspace")
    assert v.ok is False
    assert v.round_trip_ok is False
    assert any(ref.where == "render" for ref in v.refusals)


def test_roundtrip_report_wraps_reverse_ingest_refusal(monkeypatch) -> None:
    import canon.fidelity as fid
    # Fault-inject a render that emits an interior the real ingest refuses
    # (a body-less block); the reverse leg must be caught, not propagated.
    monkeypatch.setattr(
        fid, "render_region",
        lambda records, scope: '<!-- canon:block id="x" -->\n## X\n')
    v = fid.roundtrip_report([block(id="x")], "workspace")
    assert v.ok is False
    assert any(ref.where == "ingest" for ref in v.refusals)


# ---- outside preservation is computed, not defaulted --------------------------

def test_outside_preserved_runs_the_host_matrix() -> None:
    from canon.fidelity import _host_matrix_ok
    assert _host_matrix_ok() is True


def test_outside_preserved_is_wired_to_the_matrix(monkeypatch) -> None:
    import canon.fidelity as fid
    monkeypatch.setattr(fid, "_host_matrix_ok", lambda file_text=None: False)
    v = fid.roundtrip_report([block()], "workspace")
    assert v.outside_preserved is False
    assert v.ok is False  # the gate depends on the matrix leg


def test_file_text_leg_requires_a_writable_region() -> None:
    host = (
        "intro\r\n<!-- canon:begin scope=workspace -->\r\n"
        "old interior\r\n<!-- canon:end -->\r\noutro\r\n"
    )
    ok = roundtrip_report([block(id="x")], "workspace", file_text=host)
    assert ok.outside_preserved is True
    no_region = roundtrip_report([block(id="x")], "workspace",
                                 file_text="prose with no markers\n")
    assert no_region.outside_preserved is False


# ---- the gate never raises: any constructible record yields a verdict ----------
# fidelity.py promises "the verdict never propagates an exception." A malformed
# but type-constructible Record (drawn from a store or a deserialized export)
# must come back as ok=False with a render Refusal, not a traceback out of the
# R0 gate. These reproduce the confirmed audit findings at the verdict leg.

@pytest.mark.parametrize("bad_data", [None, ["title", "body"], 5])
def test_roundtrip_report_non_dict_data_is_a_verdict(bad_data: object) -> None:
    r = Record(
        kind=KIND_PERSONALITY_BLOCK, id="x", scope="workspace", data=bad_data,
        provenance=Provenance(harness="claude-code", source_hash="a" * 64,
                              create_ord=1),
        temporal=None)
    v = roundtrip_report([r], "workspace")
    assert v.ok is False
    assert any(ref.where == "render" for ref in v.refusals)


def test_roundtrip_report_none_provenance_is_a_verdict() -> None:
    r = Record(
        kind=KIND_PERSONALITY_BLOCK, id="x", scope="workspace",
        data={"title": "T", "body": "B"}, provenance=None, temporal=None)
    v = roundtrip_report([r], "workspace")
    assert v.ok is False
    assert any(ref.where == "render" for ref in v.refusals)


def test_roundtrip_report_non_int_create_ord_is_a_verdict() -> None:
    v = roundtrip_report([block(create_ord="5")], "workspace")
    assert v.ok is False
    assert any(ref.where == "render" for ref in v.refusals)


def test_roundtrip_report_cr_in_id_is_a_render_refusal() -> None:
    # render must OWN the refusal (strict-superset invariant), not defer to ingest
    v = roundtrip_report([block(id="a\rb")], "workspace")
    assert v.ok is False
    assert any(ref.where == "render" for ref in v.refusals)
    assert not any(ref.where == "ingest" for ref in v.refusals)


def test_roundtrip_report_empty_id_is_a_render_refusal() -> None:
    v = roundtrip_report([block(id="")], "workspace")
    assert v.ok is False
    assert any(ref.where == "render" for ref in v.refusals)
    assert not any(ref.where == "ingest" for ref in v.refusals)
