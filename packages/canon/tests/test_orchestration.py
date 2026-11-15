"""test_orchestration.py -- R1: writing a harness's whole surface set.

write_surfaces renders every catalog surface from one pool, choosing each
surface's content by the authored-split rule: a global file carries the
globals; a workspace file carries only workspace-authored blocks when the same
harness also has a global surface (Claude Code's two CLAUDE.md files), and the
full merged set when it does not (Codex's lone AGENTS.md). A host that has not
opted in (no canon region) is skipped and reported, never mutated.

Fake roots and injected IO keep every real path out of the repo.
"""
from __future__ import annotations

import os

from canon.registry import (
    ROOT_HOME,
    ROOT_WORKSPACE,
    SURFACE_CATALOG,
    Surface,
    resolve_surface_path,
    write_surfaces,
)
from canon.schema import KIND_PERSONALITY_BLOCK, Provenance, Record
from canon.textblock import ingest_region

HOME = os.path.join("fake", "home")
WS = os.path.join("fake", "ws")

CLAUDE_GLOBAL = Surface("claude-code", "global", ROOT_HOME, ".claude/CLAUDE.md")
CLAUDE_WS = Surface("claude-code", "workspace", ROOT_WORKSPACE, "CLAUDE.md")
AGENTS_WS = Surface("codex", "workspace", ROOT_WORKSPACE, "AGENTS.md")
SOUL_WS = Surface("hermes", "workspace", ROOT_WORKSPACE, "SOUL.md")


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

    def read_text(self, path: str) -> str:
        return self.files[path]

    def write_text(self, path: str, text: str) -> None:
        self.files[path] = text
        self.writes.append(path)


def _pool() -> list[Record]:
    return [
        _block("mission", "global", "G mission", 5),
        _block("voice", "global", "G voice", 10),
        _block("tone", "workspace", "W tone", 20),
        _block("voice", "workspace", "W voice", 30),
    ]


def _seed_all() -> FakeFS:
    """Every catalog surface opted in with an empty region of its own scope."""
    return FakeFS({
        resolve_surface_path(s, home=HOME, workspace=WS): _host(s.scope)
        for s in SURFACE_CATALOG
    })


def _run(fs: FakeFS):
    return write_surfaces(_pool(), home=HOME, workspace=WS,
                          read_text=fs.read_text, write_text=fs.write_text)


def test_global_surface_gets_globals_only():
    fs = _seed_all()
    _run(fs)
    path = resolve_surface_path(CLAUDE_GLOBAL, home=HOME, workspace=WS)
    recs = ingest_region(fs.files[path])
    assert [(r.id, r.data["body"]) for r in recs] == [
        ("mission", "G mission"), ("voice", "G voice")]
    assert all(r.scope == "global" for r in recs)


def test_two_file_workspace_is_authored_only_no_global_duplication():
    fs = _seed_all()
    _run(fs)
    path = resolve_surface_path(CLAUDE_WS, home=HOME, workspace=WS)
    recs = ingest_region(fs.files[path])
    # authored-split: workspace-authored blocks only, ordered by create_ord.
    assert [(r.id, r.data["body"]) for r in recs] == [
        ("tone", "W tone"), ("voice", "W voice")]
    # the non-overridden global "mission" lives only in the global file.
    assert "mission" not in {r.id for r in recs}


def test_single_file_workspace_gets_the_merged_set():
    fs = _seed_all()
    _run(fs)
    path = resolve_surface_path(AGENTS_WS, home=HOME, workspace=WS)
    recs = ingest_region(fs.files[path])
    # no global sibling in the catalog -> self-sufficient merged set.
    assert [(r.id, r.data["body"]) for r in recs] == [
        ("mission", "G mission"), ("tone", "W tone"), ("voice", "W voice")]
    assert all(r.scope == "workspace" for r in recs)


def test_offlimits_host_is_skipped_not_fatal():
    fs = _seed_all()
    agents = resolve_surface_path(AGENTS_WS, home=HOME, workspace=WS)
    fs.files[agents] = "no region here\n"  # not opted in

    results = _run(fs)

    by_path = {r.path: r.status for r in results}
    assert by_path[agents] == "off-limits"
    assert agents not in fs.writes
    # the two opted-in surfaces still wrote.
    assert resolve_surface_path(CLAUDE_GLOBAL, home=HOME, workspace=WS) in fs.writes
    assert resolve_surface_path(CLAUDE_WS, home=HOME, workspace=WS) in fs.writes


def test_unchanged_surfaces_are_not_rewritten_on_a_second_run():
    fs = _seed_all()
    _run(fs)
    first_writes = list(fs.writes)
    results = _run(fs)

    assert fs.writes == first_writes  # no new writes
    assert {r.status for r in results} == {"unchanged"}


def test_mis_scoped_catalog_host_fails_closed():
    import pytest

    from canon.surface import SurfaceError

    fs = _seed_all()
    # the workspace CLAUDE.md host declares a global region -- a real config
    # error; the orchestrator must refuse, not silently mis-splice.
    ws_path = resolve_surface_path(CLAUDE_WS, home=HOME, workspace=WS)
    fs.files[ws_path] = _host("global")

    with pytest.raises(SurfaceError):
        _run(fs)
    # all-or-nothing: the mis-scope is at catalog index 1, so index 0 (the
    # global CLAUDE.md) must not have been written before the refusal fires.
    assert fs.writes == []


def test_a_mis_scope_on_the_last_surface_writes_nothing():
    import pytest

    from canon.surface import SurfaceError

    fs = _seed_all()
    # mis-scope a late catalog surface (SOUL.md): the surfaces ahead of it are
    # valid, so a mid-loop write would commit them before the refusal. A
    # fail-closed batch plans every host before committing any, so nothing is
    # written when a later surface refuses.
    soul = resolve_surface_path(SOUL_WS, home=HOME, workspace=WS)
    fs.files[soul] = _host("global")

    with pytest.raises(SurfaceError):
        _run(fs)
    assert fs.writes == []


def test_a_commit_pass_io_error_leaves_earlier_writes_and_propagates():
    import pytest

    # Honest scope of the all-or-nothing guarantee (D-22): the plan pass makes
    # canon's own refusals atomic, but the commit pass writes each planned file
    # in a loop with no rollback. A real filesystem fault on a later file leaves
    # the earlier files written and propagates the error. This pins that scope,
    # so a later change that silently swallows a commit-pass IO error is caught.
    class FailOnSecondWrite(FakeFS):
        def write_text(self, path: str, text: str) -> None:
            if len(self.writes) >= 1:
                raise OSError("disk full")
            super().write_text(path, text)

    fs = FailOnSecondWrite(_seed_all().files)
    with pytest.raises(OSError):
        _run(fs)
    # exactly one file committed before the fault, and it was not rolled back.
    assert len(fs.writes) == 1


def test_a_missing_host_file_is_reported_and_never_created():
    fs = _seed_all()
    gemini = next(s for s in SURFACE_CATALOG if s.relative_path == "GEMINI.md")
    path = resolve_surface_path(gemini, home=HOME, workspace=WS)
    del fs.files[path]
    fs.read_text = lambda p: fs.files.get(p)
    results = _run(fs)
    assert {r.path: r.status for r in results}[path] == "missing"
    assert path not in fs.files and path not in fs.writes


def test_write_surfaces_refuses_a_non_catalog_surface():
    import pytest

    from canon.surface import SurfaceError

    fs = _seed_all()
    # same path as the real workspace CLAUDE.md, but a harness label that is not
    # in the catalog -- the label drives the authored-split choice, so a
    # mislabeled surface would write the wrong content to a real file.
    evil = Surface("evil", "workspace", ROOT_WORKSPACE, "CLAUDE.md")
    with pytest.raises(SurfaceError):
        write_surfaces(_pool(), home=HOME, workspace=WS,
                       read_text=fs.read_text, write_text=fs.write_text,
                       surfaces=(evil,))
    assert fs.writes == []
