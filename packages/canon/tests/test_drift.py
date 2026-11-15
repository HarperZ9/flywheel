"""test_drift.py -- V2: the rendered-surface drift check.

surface_drift re-derives a managed surface from the pool and compares it to the
on-disk region interior, returning a sha256-keyed verdict. It is read-only and
total: every refusal is a verdict, never a raise. It scores canon-owned bytes --
the region interior -- so a change to the host prose outside the markers is the
host's own, never canon drift. These tests inject fake roots and a fake
filesystem, so no real path or file reaches the repo.
"""
from __future__ import annotations

import os

from canon.drift import (
    VERDICT_DRIFT,
    VERDICT_MATCH,
    VERDICT_MISSING,
    VERDICT_OFF_LIMITS,
    VERDICT_REFUSED,
    drift_exit_code,
    drift_report,
    surface_drift,
)
from canon.registry import (
    ROOT_HOME,
    ROOT_WORKSPACE,
    SURFACE_CATALOG,
    Surface,
    resolve_surface_path,
    write_surface,
    write_surfaces,
)
from canon.schema import (
    KIND_EPISODIC_MEMORY,
    KIND_PERSONALITY_BLOCK,
    Provenance,
    Record,
)

HOME = os.path.join("fake", "home")
WS = os.path.join("fake", "ws")
CLAUDE_WS = Surface("claude-code", "workspace", ROOT_WORKSPACE, "CLAUDE.md")


def _block(id: str, scope: str, body: str, create_ord: int) -> Record:
    prov = Provenance(harness="claude-code", source_hash="a" * 64,
                      create_ord=create_ord)
    return Record(kind=KIND_PERSONALITY_BLOCK, id=id, scope=scope,
                  data={"title": id.title(), "body": body}, provenance=prov)


def _host(scope: str) -> str:
    return (
        "intro\n"
        f"<!-- canon:begin scope={scope} -->\n"
        "<!-- canon:end -->\n"
        "outro\n"
    )


class FakeFS:
    def __init__(self, files: dict[str, str]):
        self.files = dict(files)
        self.writes: list[str] = []

    def read_text(self, path: str):
        return self.files.get(path)  # None for an absent file

    def write_text(self, path: str, text: str) -> None:
        self.files[path] = text
        self.writes.append(path)


def _rendered_host(surface: Surface, pool: list[Record]):
    """A FakeFS whose surface file already holds the rendered pool (clean)."""
    path = resolve_surface_path(surface, home=HOME, workspace=WS)
    fs = FakeFS({path: _host(surface.scope)})
    write_surface(surface, pool, home=HOME, workspace=WS,
                  read_text=fs.read_text, write_text=fs.write_text)
    return path, fs


def test_clean_surface_matches():
    pool = [_block("tone", "workspace", "W tone", 20)]
    path, fs = _rendered_host(CLAUDE_WS, pool)
    d = surface_drift(CLAUDE_WS, pool, home=HOME, workspace=WS,
                      read_text=fs.read_text)
    assert d.verdict == VERDICT_MATCH
    assert d.expected_sha256 == d.actual_sha256
    assert d.expected_sha256 is not None
    assert d.path == path


def test_seeded_hand_edit_in_region_is_drift():
    pool = [_block("tone", "workspace", "W tone", 20)]
    path, fs = _rendered_host(CLAUDE_WS, pool)
    fs.files[path] = fs.files[path].replace("W tone", "W TONE hand-edited")
    d = surface_drift(CLAUDE_WS, pool, home=HOME, workspace=WS,
                      read_text=fs.read_text)
    assert d.verdict == VERDICT_DRIFT
    assert d.expected_sha256 != d.actual_sha256


def test_edit_outside_region_is_not_drift():
    pool = [_block("tone", "workspace", "W tone", 20)]
    path, fs = _rendered_host(CLAUDE_WS, pool)
    fs.files[path] = fs.files[path].replace("intro", "intro hand-authored preface")
    d = surface_drift(CLAUDE_WS, pool, home=HOME, workspace=WS,
                      read_text=fs.read_text)
    assert d.verdict == VERDICT_MATCH


def test_off_limits_host_has_no_region():
    path = resolve_surface_path(CLAUDE_WS, home=HOME, workspace=WS)
    fs = FakeFS({path: "just prose, no canon region\n"})
    d = surface_drift(CLAUDE_WS, [], home=HOME, workspace=WS,
                      read_text=fs.read_text)
    assert d.verdict == VERDICT_OFF_LIMITS


def test_mis_scoped_region_is_refused():
    path = resolve_surface_path(CLAUDE_WS, home=HOME, workspace=WS)
    fs = FakeFS({path: _host("global")})  # region global, surface workspace
    d = surface_drift(CLAUDE_WS, [], home=HOME, workspace=WS,
                      read_text=fs.read_text)
    assert d.verdict == VERDICT_REFUSED


def test_missing_file_is_missing():
    fs = FakeFS({})
    d = surface_drift(CLAUDE_WS, [], home=HOME, workspace=WS,
                      read_text=fs.read_text)
    assert d.verdict == VERDICT_MISSING


def test_deformed_marker_is_refused_not_raised():
    path = resolve_surface_path(CLAUDE_WS, home=HOME, workspace=WS)
    fs = FakeFS({path: (
        "intro\n"
        "  <!-- canon:begin scope=workspace -->\n"  # indented: a RegionError
        "<!-- canon:end -->\n"
    )})
    d = surface_drift(CLAUDE_WS, [], home=HOME, workspace=WS,
                      read_text=fs.read_text)
    assert d.verdict == VERDICT_REFUSED


def test_merged_workspace_file_drifts_from_the_authored_split():
    # The singular write_surface renders the whole pool into a surface, which for
    # a two-file harness is a merged workspace file the authored-split (D-21)
    # does not sanction. drift mirrors write_surfaces, so it flags that merge.
    pool = [_block("voice", "global", "G voice", 10),
            _block("tone", "workspace", "W tone", 20)]
    path = resolve_surface_path(CLAUDE_WS, home=HOME, workspace=WS)
    fs = FakeFS({path: _host("workspace")})
    write_surface(CLAUDE_WS, pool, home=HOME, workspace=WS,
                  read_text=fs.read_text, write_text=fs.write_text)  # merged
    d = surface_drift(CLAUDE_WS, pool, home=HOME, workspace=WS,
                      read_text=fs.read_text)
    assert d.verdict == VERDICT_DRIFT


def test_mixed_pool_with_non_block_record_is_refused_not_raised():
    # D-58: layering rejects a non-personality-block record inside the pool,
    # and that raise reaches surface_drift through render_surface. drift must
    # fold the layering refusal into a verdict, never leak, so the totality
    # guarantee ("every refusal is a verdict") holds for a realistic mixed
    # pool a caller supplies (e.g. personality blocks alongside episodic
    # memories from the same store).
    ep = Record(kind=KIND_EPISODIC_MEMORY, id="ep-1", scope="workspace",
                data={"body": "a raw turn"},
                provenance=Provenance(harness="claude-code",
                                      source_hash="b" * 64, create_ord=5))
    pool = [_block("tone", "workspace", "W tone", 20), ep]
    path = resolve_surface_path(CLAUDE_WS, home=HOME, workspace=WS)
    fs = FakeFS({path: _host("workspace")})
    d = surface_drift(CLAUDE_WS, pool, home=HOME, workspace=WS,
                      read_text=fs.read_text)
    assert d.verdict == VERDICT_REFUSED
    assert d.reason is not None
    assert "personality-block" in d.reason


def test_drift_report_over_mixed_pool_does_not_raise():
    # The whole-catalog report must also stay total when the pool carries a
    # non-personality-block record. Every surface refuses, the report is not
    # ok, and the exit code is one -- no LayeringError leaks out of drift.
    ep = Record(kind=KIND_EPISODIC_MEMORY, id="ep-1", scope="workspace",
                data={"body": "a raw turn"},
                provenance=Provenance(harness="claude-code",
                                      source_hash="b" * 64, create_ord=5))
    pool = [_block("tone", "workspace", "W tone", 20), ep]
    files = {resolve_surface_path(s, home=HOME, workspace=WS): _host(s.scope)
             for s in SURFACE_CATALOG}
    fs = FakeFS(files)
    report = drift_report(pool, home=HOME, workspace=WS,
                          read_text=fs.read_text)
    assert not report.ok
    assert drift_exit_code(report) == 1
    assert all(d.verdict == VERDICT_REFUSED for d in report.surfaces)


def test_drift_report_mirrors_write_surfaces_and_exit_code():
    # drift must mirror the deployed writer. write_surfaces applies the
    # authored-split (pool_for) per surface, so a clean baseline is built by it,
    # not by the singular write_surface (which renders the whole pool it is
    # handed). A pool with a global AND a workspace block makes the two diverge
    # on the claude-code workspace surface, which is exactly what drift guards.
    pool = [_block("voice", "global", "G voice", 10),
            _block("tone", "workspace", "W tone", 20)]
    files = {resolve_surface_path(s, home=HOME, workspace=WS): _host(s.scope)
             for s in SURFACE_CATALOG}
    fs = FakeFS(files)
    write_surfaces(pool, home=HOME, workspace=WS,
                   read_text=fs.read_text, write_text=fs.write_text)

    report = drift_report(pool, home=HOME, workspace=WS, read_text=fs.read_text)
    assert report.ok
    assert drift_exit_code(report) == 0
    assert len(report.surfaces) == len(SURFACE_CATALOG)

    cp = resolve_surface_path(CLAUDE_WS, home=HOME, workspace=WS)
    fs.files[cp] = fs.files[cp].replace("W tone", "W drifted")
    drifted = drift_report(pool, home=HOME, workspace=WS, read_text=fs.read_text)
    assert not drifted.ok
    assert drift_exit_code(drifted) == 1
    assert any(d.verdict == VERDICT_DRIFT for d in drifted.surfaces)
