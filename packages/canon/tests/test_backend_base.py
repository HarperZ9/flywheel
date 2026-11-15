"""The storage seam itself: keys, capability arithmetic, and the shared guard.

These pin base.py independently of any concrete store: record_key/split_key are
exact inverses (even when an id contains a slash), temporal is the one
record-enforceable capability, flatten strips only what is removable, and
guard_put raises the right error for the right reason. The four adapters are
checked here only for Protocol conformance (isinstance against the
runtime_checkable MemoryBackend); their round-trips live in their own modules.
"""
from __future__ import annotations

import pytest

from canon.backends import (
    CAP_TEMPORAL,
    CAPABILITIES,
    RECORD_ENFORCEABLE,
    BackendError,
    DropError,
    FilesBackend,
    FlywheelBackend,
    MemoryBackend,
    MnemeBackend,
    SqliteBackend,
    UnsupportedKind,
    capabilities_required,
    flatten_for_drops,
    guard_put,
    record_key,
    split_key,
    temporal_in_use,
)
from canon.schema import Provenance, Record, Temporal

from ._fakes import FakeFlywheelStore, FakeMnemeStore
from ._helpers import RECORD_FILES, load_record


def _block(scope: str = "global", rid: str = "b") -> Record:
    return Record(
        kind="personality-block", id=rid, scope=scope,
        data={"title": "t", "body": "b"},
        provenance=Provenance(harness="author", source_hash="a" * 64))


def test_record_key_is_scope_then_id() -> None:
    assert record_key(_block("workspace", "voice-canon")) == "workspace/voice-canon"


def test_split_key_inverts_record_key() -> None:
    rec = _block("workspace", "voice-canon")
    assert split_key(record_key(rec)) == ("workspace", "voice-canon")


def test_split_key_keeps_slash_in_id() -> None:
    # id may contain '/'; only the first separator delimits scope.
    assert split_key("global/a/b/c") == ("global", "a/b/c")


def test_two_scopes_one_id_are_distinct_keys() -> None:
    # The override case: one block id present at both scopes must not collide.
    g = record_key(_block("global", "voice-canon"))
    w = record_key(_block("workspace", "voice-canon"))
    assert g != w


def test_temporal_in_use_only_when_history_present() -> None:
    assert temporal_in_use(load_record(RECORD_FILES["synthesized-persona-l3"]))
    # An all-null temporal block carries no history.
    assert not temporal_in_use(load_record(RECORD_FILES["episodic-memory"]))
    # An absent temporal block likewise.
    assert not temporal_in_use(load_record(RECORD_FILES["research-artifact-ref"]))


def test_valid_until_alone_counts_as_in_use() -> None:
    rec = _block().with_temporal(Temporal(valid_until=5, supersedes=None))
    assert temporal_in_use(rec)


def test_capabilities_required_is_temporal_or_empty() -> None:
    live = load_record(RECORD_FILES["synthesized-persona-l3"])
    assert capabilities_required(live) == frozenset({CAP_TEMPORAL})
    assert capabilities_required(load_record(RECORD_FILES["episodic-memory"])) == frozenset()


def test_record_enforceable_is_exactly_temporal() -> None:
    assert RECORD_ENFORCEABLE == frozenset({CAP_TEMPORAL})
    assert RECORD_ENFORCEABLE <= CAPABILITIES


def test_flatten_strips_temporal_only_when_dropped_and_in_use() -> None:
    live = load_record(RECORD_FILES["synthesized-persona-l3"])
    flat = flatten_for_drops(live, frozenset({CAP_TEMPORAL}))
    assert flat.temporal is None
    # Not dropped -> unchanged (same object is acceptable; identity of history).
    assert flatten_for_drops(live, frozenset()).temporal is not None
    # Dropped but not in use -> unchanged.
    calm = load_record(RECORD_FILES["episodic-memory"])
    assert flatten_for_drops(calm, frozenset({CAP_TEMPORAL})) is calm


def test_flatten_does_not_mutate_source() -> None:
    live = load_record(RECORD_FILES["synthesized-persona-l3"])
    flatten_for_drops(live, frozenset({CAP_TEMPORAL}))
    assert live.temporal is not None  # frozen; with_temporal returns a copy


def test_error_hierarchy() -> None:
    assert issubclass(UnsupportedKind, BackendError)
    assert issubclass(DropError, BackendError)
    assert issubclass(BackendError, Exception)


def test_guard_put_passes_supported_calm_record(tmp_path) -> None:
    be = SqliteBackend(tmp_path / "guard.sqlite")
    guard_put(be, load_record(RECORD_FILES["adr-decision"]))  # no raise


def test_guard_put_raises_unsupported_kind() -> None:
    be = MnemeBackend(FakeMnemeStore())
    with pytest.raises(UnsupportedKind):
        guard_put(be, load_record(RECORD_FILES["personality-block"]))


def test_guard_put_raises_drop_error_on_temporal() -> None:
    be = FlywheelBackend(FakeFlywheelStore())
    with pytest.raises(DropError):
        guard_put(be, load_record(RECORD_FILES["synthesized-persona-l3"]))


def test_all_four_backends_satisfy_protocol(tmp_path) -> None:
    backends = [
        FilesBackend(tmp_path / "files"),
        SqliteBackend(tmp_path / "s.sqlite"),
        MnemeBackend(FakeMnemeStore()),
        FlywheelBackend(FakeFlywheelStore()),
    ]
    for be in backends:
        assert isinstance(be, MemoryBackend)
        assert isinstance(be.name, str) and be.name
