"""Layering proof: the pool resolves to the stated effective set per scope.

The F0 exit criterion is that resolve_blocks over the layering pool fixture
produces exactly the effective block list recorded in layering_expected.json,
for both render scopes, in the stated order -- proving override-by-id,
scope containment, in-place supersede collapse, and superseded exclusion all
hold at once.
"""
from __future__ import annotations

import pytest

from canon.layering import LayeringError, is_current, resolve_blocks
from canon.schema import (
    KIND_EPISODIC_MEMORY,
    Provenance,
    Record,
    Temporal,
)

from ._helpers import FIXTURES, load_dict


def _pool() -> list[Record]:
    raw = load_dict(FIXTURES / "layering_pool.json")
    return [Record.from_dict(d) for d in raw]


def _expected(scope: str) -> list[tuple[str, str]]:
    exp = load_dict(FIXTURES / "layering_expected.json")
    return [tuple(pair) for pair in exp[scope]]


@pytest.mark.parametrize("scope", ["global", "workspace"])
def test_effective_set_matches_fixture(scope: str) -> None:
    effective = resolve_blocks(_pool(), scope)
    got = [(r.id, r.scope) for r in effective]
    assert got == _expected(scope)


def test_workspace_override_returns_the_workspace_copy() -> None:
    effective = {r.id: r for r in resolve_blocks(_pool(), "workspace")}
    assert effective["voice"].scope == "workspace"
    assert "override" in effective["voice"].data["title"]


def test_global_render_excludes_workspace_only_blocks() -> None:
    ids = {r.id for r in resolve_blocks(_pool(), "global")}
    assert "shipping" not in ids
    assert "deprecated" not in ids


def test_superseded_in_place_block_is_replaced_by_current() -> None:
    effective = {r.id: r for r in resolve_blocks(_pool(), "global")}
    # "testing" appears twice at global (superseded ord 2, current ord 9);
    # the current one must win.
    assert effective["testing"].data["title"] == "Testing (current)"
    assert is_current(effective["testing"])


def test_superseded_workspace_block_is_absent() -> None:
    ids = {r.id for r in resolve_blocks(_pool(), "workspace")}
    assert "deprecated" not in ids


def test_effective_order_is_by_create_ord() -> None:
    ords = [r.provenance.create_ord for r in resolve_blocks(_pool(), "workspace")]
    assert ords == sorted(ords)


def test_non_block_record_is_rejected() -> None:
    intruder = Record(
        kind=KIND_EPISODIC_MEMORY,
        id="mem-1",
        scope="global",
        data={"layer": "L0", "text": "x", "source_ids": []},
        provenance=Provenance(harness="mneme", source_hash="a" * 64),
    )
    with pytest.raises(LayeringError):
        resolve_blocks([intruder], "global")


def test_unknown_scope_is_rejected() -> None:
    with pytest.raises(LayeringError):
        resolve_blocks(_pool(), "repo")


def test_no_temporal_block_counts_as_current() -> None:
    rec = Record(
        kind="personality-block",
        id="b",
        scope="global",
        data={"title": "t", "body": "b"},
        provenance=Provenance(harness="author", source_hash="a" * 64, create_ord=1),
        temporal=None,
    )
    assert is_current(rec)
    assert [r.id for r in resolve_blocks([rec], "global")] == ["b"]


def test_retired_workspace_override_falls_back_to_global() -> None:
    # A current global block and a fully-superseded workspace override of the
    # same id: the workspace override no longer applies, so the workspace
    # render must fall back to the global block, not suppress the id.
    global_voice = Record(
        kind="personality-block",
        id="voice",
        scope="global",
        data={"title": "Voice (global)", "body": "g"},
        provenance=Provenance(harness="author", source_hash="a" * 64, create_ord=1),
        temporal=Temporal(valid_until=None, supersedes=None),
    )
    retired_ws_voice = Record(
        kind="personality-block",
        id="voice",
        scope="workspace",
        data={"title": "Voice (retired workspace override)", "body": "w"},
        provenance=Provenance(harness="author", source_hash="a" * 64, create_ord=5),
        temporal=Temporal(valid_until=8, supersedes=None),
    )
    effective = resolve_blocks([global_voice, retired_ws_voice], "workspace")
    assert [(r.id, r.scope) for r in effective] == [("voice", "global")]


def test_equal_ord_current_duplicates_resolve_order_independently() -> None:
    # Two current blocks share one (scope, id) with equal create_ord (a
    # malformed pool). The survivor must be decided by the source_hash
    # tie-break, not by which record appears first in the list.
    a = Record(
        kind="personality-block",
        id="dup",
        scope="global",
        data={"title": "A", "body": "a"},
        provenance=Provenance(harness="author", source_hash="a" * 64, create_ord=5),
    )
    b = Record(
        kind="personality-block",
        id="dup",
        scope="global",
        data={"title": "B", "body": "b"},
        provenance=Provenance(harness="author", source_hash="b" * 64, create_ord=5),
    )
    forward = [r.data["title"] for r in resolve_blocks([a, b], "global")]
    backward = [r.data["title"] for r in resolve_blocks([b, a], "global")]
    assert forward == backward


def test_current_temporal_with_null_valid_until_is_current() -> None:
    rec = Record(
        kind="personality-block",
        id="b",
        scope="global",
        data={"title": "t", "body": "b"},
        provenance=Provenance(harness="author", source_hash="a" * 64, create_ord=1),
        temporal=Temporal(valid_until=None, supersedes="older"),
    )
    assert is_current(rec)
