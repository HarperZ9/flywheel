"""The declared-drops contract, pinned across all four backends at once.

Each backend must name exactly what a round-trip through it loses, in capability
tokens drawn from the fixed vocabulary. This module fixes the four profiles as a
single table and checks the one enforcement rule that spans them: a
record-enforceable capability (temporal) refused at put time when dropped, a
structural capability (audit-chain, arbitrary-kind, relations,
foreign-provenance) declared but never able to block a lone put.
"""
from __future__ import annotations

import pytest

from canon.backends import (
    CAP_ARBITRARY_KIND,
    CAP_AUDIT_CHAIN,
    CAP_FOREIGN_PROVENANCE,
    CAP_RELATIONS,
    CAP_TEMPORAL,
    CAPABILITIES,
    DropError,
    FilesBackend,
    FlywheelBackend,
    MnemeBackend,
    SqliteBackend,
    UnsupportedKind,
)

from ._fakes import FakeFlywheelStore, FakeMnemeStore
from ._helpers import RECORD_FILES, earlier_persona, load_record

EXPECTED = {
    "files": frozenset({CAP_AUDIT_CHAIN}),
    "sqlite": frozenset(),
    "flywheel": frozenset({CAP_TEMPORAL}),
    "mneme": frozenset({CAP_ARBITRARY_KIND, CAP_RELATIONS, CAP_FOREIGN_PROVENANCE}),
}


def _all(tmp_path) -> list:
    return [
        FilesBackend(tmp_path / "files"),
        SqliteBackend(tmp_path / "s.sqlite"),
        FlywheelBackend(FakeFlywheelStore()),
        MnemeBackend(FakeMnemeStore()),
    ]


def test_each_backend_declares_its_exact_profile(tmp_path) -> None:
    for be in _all(tmp_path):
        assert be.declared_drops() == EXPECTED[be.name], be.name


def test_every_declared_drop_is_a_known_capability(tmp_path) -> None:
    for be in _all(tmp_path):
        assert be.declared_drops() <= CAPABILITIES, be.name


def test_temporal_record_refused_only_where_temporal_is_dropped(tmp_path) -> None:
    live = load_record(RECORD_FILES["synthesized-persona-l3"])  # 0004 -> 0003
    for be in _all(tmp_path):
        if CAP_TEMPORAL in be.declared_drops():
            with pytest.raises(DropError):
                be.put(live)
        elif live.kind in be.supported_kinds():
            # mneme links a supersession only to a present row, so its ordering
            # precondition (store the target first) is met before the live put.
            if be.name == "mneme":
                be.put(earlier_persona())
            be.put(live)  # kept faithfully, no raise


def test_structural_drop_never_blocks_a_put(tmp_path) -> None:
    # files drops audit-chain (structural); an ordinary put must still succeed.
    be = FilesBackend(tmp_path / "files")
    be.put(load_record(RECORD_FILES["adr-decision"]))  # no DropError


def test_mneme_refuses_kinds_outside_its_two(tmp_path) -> None:
    be = MnemeBackend(FakeMnemeStore())
    for kind in ("personality-block", "adr-decision", "research-artifact-ref"):
        with pytest.raises(UnsupportedKind):
            be.put(load_record(RECORD_FILES[kind]))


def test_zero_drop_backend_keeps_everything(tmp_path) -> None:
    # sqlite drops nothing: it accepts the live-temporal record unflattened.
    be = SqliteBackend(tmp_path / "s.sqlite")
    live = load_record(RECORD_FILES["synthesized-persona-l3"])
    be.put(live)
    assert be.get("global/persona-operator-0004").temporal is not None
