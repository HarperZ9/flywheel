"""test_surface.py -- R1: the pool -> host-file surface renderer.

apply_surface resolves the canonical pool for a target scope, projects the
effective (mixed-origin) set onto that scope, renders it, and splices it into a
managed host file's region -- the composition that turns the store's block set
into the bytes a harness reads.
"""
from __future__ import annotations

import pytest

from canon.schema import KIND_PERSONALITY_BLOCK, Provenance, Record, Temporal
from canon.surface import SurfaceError, apply_surface
from canon.textblock import ingest_region


def _block(id: str, scope: str, body: str, create_ord: int,
           sup: str | None = None, valid_until: int | None = None) -> Record:
    prov = Provenance(harness="claude-code", source_hash="a" * 64,
                      native_id=f"block:{id}", create_ord=create_ord)
    temporal = None
    if sup is not None or valid_until is not None:
        temporal = Temporal(valid_until=valid_until, supersedes=sup)
    return Record(kind=KIND_PERSONALITY_BLOCK, id=id, scope=scope,
                  data={"title": id.title(), "body": body},
                  provenance=prov, temporal=temporal)


def gblock(id: str, body: str, create_ord: int, **kw) -> Record:
    return _block(id, "global", body, create_ord, **kw)


def wblock(id: str, body: str, create_ord: int, **kw) -> Record:
    return _block(id, "workspace", body, create_ord, **kw)


HOST_WORKSPACE = (
    "intro prose\n"
    "<!-- canon:begin scope=workspace -->\n"
    "<!-- canon:end -->\n"
    "outro prose\n"
)

HOST_GLOBAL = (
    "intro prose\n"
    "<!-- canon:begin scope=global -->\n"
    "<!-- canon:end -->\n"
    "outro prose\n"
)

HOST_OFFLIMITS = "just prose, no canon region here\n"


def test_apply_surface_writes_resolved_blocks_and_preserves_outside():
    pool = [gblock("voice", "Global voice", create_ord=10),
            wblock("tone", "Workspace tone", create_ord=20)]

    out = apply_surface(HOST_WORKSPACE, pool, "workspace")

    assert out.startswith("intro prose\n")
    assert out.endswith("outro prose\n")
    recs = ingest_region(out)
    assert [r.id for r in recs] == ["voice", "tone"]
    assert all(r.scope == "workspace" for r in recs)


def test_apply_surface_refuses_region_scope_mismatch():
    pool = [wblock("tone", "Workspace tone", create_ord=20)]
    with pytest.raises(SurfaceError):
        apply_surface(HOST_GLOBAL, pool, "workspace")


def test_apply_surface_refuses_offlimits_host():
    with pytest.raises(SurfaceError):
        apply_surface(HOST_OFFLIMITS, [], "workspace")


def test_workspace_override_wins_in_the_workspace_surface():
    pool = [gblock("voice", "Global voice", create_ord=10),
            wblock("voice", "Workspace voice", create_ord=30)]
    recs = ingest_region(apply_surface(HOST_WORKSPACE, pool, "workspace"))
    assert [r.id for r in recs] == ["voice"]
    assert recs[0].data["body"] == "Workspace voice"
    assert recs[0].scope == "workspace"


def test_global_surface_excludes_workspace_blocks():
    pool = [gblock("voice", "Global voice", create_ord=10),
            wblock("tone", "Workspace tone", create_ord=20)]
    recs = ingest_region(apply_surface(HOST_GLOBAL, pool, "global"))
    assert [r.id for r in recs] == ["voice"]
    assert all(r.scope == "global" for r in recs)


def test_apply_surface_is_idempotent():
    pool = [gblock("voice", "Global voice", create_ord=10),
            wblock("tone", "Workspace tone", create_ord=20)]
    once = apply_surface(HOST_WORKSPACE, pool, "workspace")
    twice = apply_surface(once, pool, "workspace")
    assert twice == once


def test_region_ingests_back_to_the_resolved_view_in_order():
    pool = [gblock("voice", "Global voice", create_ord=10),
            wblock("voice", "Workspace voice", create_ord=30),
            wblock("tone", "Workspace tone", create_ord=20)]
    recs = ingest_region(apply_surface(HOST_WORKSPACE, pool, "workspace"))
    # resolved workspace view: override voice(ord 30) + tone(ord 20),
    # ordered by create_ord ascending -> tone, then voice.
    assert [(r.id, r.data["body"]) for r in recs] == [
        ("tone", "Workspace tone"), ("voice", "Workspace voice")]


def test_empty_pool_renders_empty_region_preserving_outside():
    out = apply_surface(HOST_WORKSPACE, [], "workspace")
    assert out.startswith("intro prose\n")
    assert out.endswith("outro prose\n")
    assert ingest_region(out) == []


def test_superseded_block_is_excluded_from_the_surface():
    pool = [gblock("voice", "Global voice", create_ord=10, valid_until=50),
            wblock("tone", "Workspace tone", create_ord=20)]
    recs = ingest_region(apply_surface(HOST_WORKSPACE, pool, "workspace"))
    assert [r.id for r in recs] == ["tone"]


def test_non_personality_block_in_pool_is_a_layering_error():
    from canon.layering import LayeringError
    bad = Record(kind="episodic-memory", id="m1", scope="workspace",
                 data={"text": "x"},
                 provenance=Provenance(harness="h", source_hash="a" * 64))
    with pytest.raises(LayeringError):
        apply_surface(HOST_WORKSPACE, [bad], "workspace")


def test_surface_render_passes_the_r0_fidelity_gate():
    from dataclasses import replace

    from canon.fidelity import roundtrip_report
    from canon.layering import resolve_blocks

    pool = [gblock("voice", "Global voice", create_ord=10),
            wblock("voice", "Workspace voice", create_ord=30),
            wblock("tone", "Workspace tone", create_ord=20)]
    projected = [replace(r, scope="workspace")
                 for r in resolve_blocks(pool, "workspace")]

    verdict = roundtrip_report(projected, "workspace", file_text=HOST_WORKSPACE)

    assert verdict.ok
    assert verdict.refusals == ()
    assert not any(loss.kind == "UNDECLARED" for loss in verdict.losses)
