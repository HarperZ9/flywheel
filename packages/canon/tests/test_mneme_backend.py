"""MnemeBackend: the temporal home, mapped over an injected mneme Store.

mneme holds the two memory kinds and keeps their history. What round-trips:
content (layer/text/source_ids/extractor/criterion), scope (via mneme's user
column), session, and temporal supersession. What does not: a foreign
provenance receipt -- mneme derives provenance from its own row columns, so
source_hash and create_ord come back re-derived, not the values a foreign
harness wrote. Every non-memory kind is refused outright (arbitrary-kind drop).

The store here is FakeMnemeStore, which mirrors the real mneme surface read from
source: source_ids stored as JSON text, a content-hash collision guard, a
monotonic ordinal, and supersede() setting valid_until + superseded_by.
"""
from __future__ import annotations

import pytest

from canon.backends import (
    BackendError,
    DropError,
    MissingSupersedeTarget,
    MnemeBackend,
    UnsupportedKind,
    record_key,
)
from canon.schema import (
    KIND_EPISODIC_MEMORY,
    KIND_SYNTHESIZED_PERSONA_L3,
    Temporal,
)

from ._fakes import FakeMnemeStore
from ._helpers import RECORD_FILES, earlier_persona, load_record


def _backend() -> tuple[MnemeBackend, FakeMnemeStore]:
    store = FakeMnemeStore()
    return MnemeBackend(store), store


def test_supported_kinds_are_the_two_memory_kinds() -> None:
    be, _ = _backend()
    assert be.supported_kinds() == frozenset(
        {KIND_EPISODIC_MEMORY, KIND_SYNTHESIZED_PERSONA_L3})


def test_content_scope_session_roundtrip() -> None:
    be, _ = _backend()
    rec = load_record(RECORD_FILES["episodic-memory"])
    be.put(rec)
    got = be.get(record_key(rec))
    assert got is not None
    assert got.kind == rec.kind
    assert got.data == rec.data                       # layer/text/source_ids/...
    assert got.scope == rec.scope                     # global, via user column
    assert got.provenance.session_id == rec.provenance.session_id


def test_source_ids_survive_json_layer() -> None:
    be, _ = _backend()
    rec = load_record(RECORD_FILES["episodic-memory"])
    be.put(rec)
    got = be.get(record_key(rec))
    assert got.data["source_ids"] == ["turn-0007", "turn-0009"]


def test_foreign_provenance_is_dropped_and_re_derived() -> None:
    be, store = _backend()
    rec = load_record(RECORD_FILES["episodic-memory"])
    be.put(rec)
    got = be.get(record_key(rec))
    row = store.memory("mem-000123")
    # Re-derived from mneme's own columns, not the foreign receipt.
    assert got.provenance.source_hash == row["content_sha256"]
    assert got.provenance.create_ord == row["created_ord"]
    # And therefore not the values the fixture's foreign harness wrote.
    assert got.provenance.source_hash != rec.provenance.source_hash
    assert got.provenance.create_ord != rec.provenance.create_ord
    # mneme-native fields still carry through.
    assert got.provenance.harness == "mneme"
    assert got.provenance.native_id == "mneme:mem-000123"


def test_refuses_non_memory_kind() -> None:
    be, _ = _backend()
    with pytest.raises(UnsupportedKind):
        be.put(load_record(RECORD_FILES["personality-block"]))
    with pytest.raises(UnsupportedKind):
        be.put(load_record(RECORD_FILES["adr-decision"]))


def test_supersede_pair_roundtrips_both_directions() -> None:
    be, _ = _backend()
    older = earlier_persona()                                   # 0003
    newer = load_record(RECORD_FILES["synthesized-persona-l3"])  # 0004 -> 0003
    be.put(older)
    be.put(newer)

    got_new = be.get(record_key(newer))
    assert got_new.temporal is not None
    assert got_new.temporal.supersedes == "persona-operator-0003"
    assert got_new.temporal.valid_until is None                # current

    got_old = be.get(record_key(older))
    assert got_old.temporal is not None
    assert got_old.temporal.valid_until is not None            # superseded
    assert got_old.temporal.supersedes is None                 # nothing before it


def test_records_lists_current_and_superseded() -> None:
    be, _ = _backend()
    be.put(earlier_persona())
    be.put(load_record(RECORD_FILES["synthesized-persona-l3"]))
    ids = {r.id for r in be.records()}
    assert ids == {"persona-operator-0003", "persona-operator-0004"}


def test_incoming_valid_until_is_refused_not_silently_dropped() -> None:
    # mneme assigns the supersession ordinal from its own clock, so it cannot
    # store a caller-supplied valid_until. It must refuse loudly, not store the
    # record as current (which would resurrect a retired fact).
    be, _ = _backend()
    older = earlier_persona()
    retired = older.with_temporal(Temporal(valid_until=191, supersedes=None))
    with pytest.raises(DropError):
        be.put(retired)


def test_supersede_target_absent_is_refused() -> None:
    # 0004 supersedes 0003, but 0003 was never stored. mneme links only to a
    # present current row, so this is refused rather than silently no-op'd.
    be, _ = _backend()
    newer = load_record(RECORD_FILES["synthesized-persona-l3"])  # 0004 -> 0003
    with pytest.raises(MissingSupersedeTarget):
        be.put(newer)


def test_flatten_strips_valid_until_and_keeps_supersedes() -> None:
    be, _ = _backend()
    rec = load_record(RECORD_FILES["synthesized-persona-l3"])   # 0004 -> 0003
    retired = rec.with_temporal(Temporal(valid_until=200, supersedes="persona-operator-0003"))
    flat = be.flatten(retired)
    assert flat.temporal is not None
    assert flat.temporal.valid_until is None
    assert flat.temporal.supersedes == "persona-operator-0003"


def test_flatten_of_lone_valid_until_nulls_temporal() -> None:
    be, _ = _backend()
    rec = earlier_persona()
    retired = rec.with_temporal(Temporal(valid_until=191, supersedes=None))
    flat = be.flatten(retired)
    assert flat.temporal is None


def test_flattened_retired_record_stores_and_keeps_link() -> None:
    # The opt-in path: a record retired in the source (valid_until set) that
    # also supersedes a present row. put() refuses it; the caller flatten()s and
    # re-puts; the supersede link survives, the value mneme cannot hold does not.
    be, _ = _backend()
    be.put(earlier_persona())                                  # 0003 present
    rec = load_record(RECORD_FILES["synthesized-persona-l3"])
    retired = rec.with_temporal(Temporal(valid_until=200, supersedes="persona-operator-0003"))
    with pytest.raises(DropError):
        be.put(retired)
    be.put(be.flatten(retired))
    got = be.get(record_key(rec))
    assert got.temporal.supersedes == "persona-operator-0003"
    assert got.temporal.valid_until is None


def test_same_id_different_content_raises_backend_error() -> None:
    # mneme's own content-collision guard raises ValueError; the adapter surfaces
    # it as a BackendError so a caller catches one refusal type, not a raw one.
    be, _ = _backend()
    rec = load_record(RECORD_FILES["episodic-memory"])
    be.put(rec)
    changed = rec.to_dict()
    changed["data"]["text"] = "A different body under the same id."
    from canon.schema import Record as _R
    with pytest.raises(BackendError):
        be.put(_R.from_dict(changed))


def test_same_content_reput_is_accepted() -> None:
    # Characterization test locking in verified real-mneme semantics: add_memory
    # is INSERT OR REPLACE, so an identical re-put is accepted (it does not raise
    # and does not diverge). Guards against a future "idempotency" change that
    # would break parity with the engine.
    be, _ = _backend()
    rec = load_record(RECORD_FILES["episodic-memory"])
    be.put(rec)
    be.put(rec)                                                # no raise
    assert be.get(record_key(rec)) is not None


def test_persona_layer_maps_to_persona_kind() -> None:
    be, _ = _backend()
    be.put(earlier_persona())                                  # 0003 target present
    be.put(load_record(RECORD_FILES["synthesized-persona-l3"]))
    got = be.get("global/persona-operator-0004")
    assert got.kind == KIND_SYNTHESIZED_PERSONA_L3


def test_get_missing_returns_none() -> None:
    be, _ = _backend()
    assert be.get("global/nope") is None
