"""FlywheelBackend: authored and graph kinds over an injected flywheel store.

flywheel holds the whole canonical envelope in its opaque data blob, so a calm
record (no live temporal history) round-trips field-identical -- provenance
included, unlike mneme. Its one drop is temporal: flywheel's entities table has
no history columns, so a record carrying a live supersede is refused by put().
The caller opts into the loss explicitly by flatten()-ing first, after which the
same record stores current-only with its temporal block stripped to null.
"""
from __future__ import annotations

import pytest

from canon.backends import (
    CAP_TEMPORAL,
    DropError,
    FlywheelBackend,
    record_key,
)
from canon.schema import KINDS

from ._fakes import FakeFlywheelStore
from ._helpers import RECORD_FILES, load_dict, load_record


def _backend() -> FlywheelBackend:
    return FlywheelBackend(FakeFlywheelStore())


def test_supports_every_kind() -> None:
    assert _backend().supported_kinds() == frozenset(KINDS)


def test_declared_drop_is_temporal_only() -> None:
    assert _backend().declared_drops() == frozenset({CAP_TEMPORAL})


@pytest.mark.parametrize("kind", ["personality-block", "adr-decision",
                                  "research-artifact-ref", "episodic-memory"])
def test_calm_record_roundtrips_field_identical(kind: str) -> None:
    # Every kind whose temporal block is absent or all-null keeps the full
    # envelope, provenance and all.
    be = _backend()
    rec = load_record(RECORD_FILES[kind])
    be.put(rec)
    got = be.get(record_key(rec))
    assert got is not None
    assert got.to_dict() == load_dict(RECORD_FILES[kind])


def test_put_refuses_live_temporal_record() -> None:
    be = _backend()
    live = load_record(RECORD_FILES["synthesized-persona-l3"])  # supersedes set
    with pytest.raises(DropError):
        be.put(live)


def test_flatten_then_put_stores_current_only() -> None:
    be = _backend()
    live = load_record(RECORD_FILES["synthesized-persona-l3"])
    flat = be.flatten(live)
    assert flat.temporal is None
    be.put(flat)                                     # no raise now
    got = be.get(record_key(live))
    assert got is not None
    assert got.temporal is None
    # Everything but temporal is preserved.
    expect = load_dict(RECORD_FILES["synthesized-persona-l3"])
    expect["temporal"] = None
    assert got.to_dict() == expect


def test_get_missing_returns_none() -> None:
    assert _backend().get("global/nope") is None


def test_records_spans_both_scopes() -> None:
    be = _backend()
    be.put(load_record(RECORD_FILES["episodic-memory"]))      # scope=global
    be.put(load_record(RECORD_FILES["personality-block"]))    # scope=workspace
    got = be.records()
    assert {r.id for r in got} == {"mem-000123", "voice-canon"}


def test_reput_upserts_same_key() -> None:
    be = _backend()
    rec = load_record(RECORD_FILES["adr-decision"])
    be.put(rec)
    be.put(rec)
    assert len(be.records()) == 1
