"""test_registry.py -- R1: the write-surface allow-list.

The renderer may rewrite ONLY the managed instruction files in the fixed
catalog. Every surface names a harness, a scope, the root it lives under (the
home directory or the workspace root), and a path relative to that root. The
absolute roots are injected at call time and never stored, so this public
catalog carries no operator path. These tests inject fake roots for the same
reason: no real path reaches the repo.
"""
from __future__ import annotations

import os

import pytest

from canon.registry import (
    ROOT_HOME,
    ROOT_WORKSPACE,
    SURFACE_CATALOG,
    Surface,
    allowed_paths,
    assert_writable,
    is_write_allowed,
    pool_for,
    resolve_surface_path,
    write_surface,
)
from canon.schema import KIND_PERSONALITY_BLOCK, Provenance, Record
from canon.surface import SurfaceError
from canon.textblock import ingest_region

HOME = os.path.join("fake", "home")
WS = os.path.join("fake", "ws")


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


def test_catalog_covers_the_confirmed_instruction_surfaces():
    coords = {(s.harness, s.scope, s.root, s.relative_path)
              for s in SURFACE_CATALOG}
    assert ("claude-code", "global", ROOT_HOME, ".claude/CLAUDE.md") in coords
    assert ("claude-code", "workspace", ROOT_WORKSPACE, "CLAUDE.md") in coords
    assert ("codex", "workspace", ROOT_WORKSPACE, "AGENTS.md") in coords


def test_resolve_surface_path_joins_the_injected_root():
    surface = Surface("claude-code", "global", ROOT_HOME, ".claude/CLAUDE.md")
    got = resolve_surface_path(surface, home=HOME, workspace=WS)
    assert got == os.path.normpath(os.path.join(HOME, ".claude/CLAUDE.md"))


def test_allowed_paths_are_exactly_the_catalog_resolved():
    got = allowed_paths(home=HOME, workspace=WS)
    want = {resolve_surface_path(s, home=HOME, workspace=WS)
            for s in SURFACE_CATALOG}
    assert got == want


def test_is_write_allowed_accepts_a_catalog_surface_path():
    path = os.path.join(WS, "CLAUDE.md")
    assert is_write_allowed(path, home=HOME, workspace=WS)


def test_is_write_allowed_refuses_a_non_surface_path():
    secret = os.path.join(HOME, ".ssh", "config")
    assert not is_write_allowed(secret, home=HOME, workspace=WS)
    with pytest.raises(SurfaceError):
        assert_writable(secret, home=HOME, workspace=WS)


def test_is_write_allowed_refuses_a_traversal_escape():
    escape = os.path.join(WS, "..", "secret.md")
    assert not is_write_allowed(escape, home=HOME, workspace=WS)


def test_write_surface_writes_through_an_allow_listed_surface():
    surface = Surface("claude-code", "workspace", ROOT_WORKSPACE, "CLAUDE.md")
    path = resolve_surface_path(surface, home=HOME, workspace=WS)
    fs = FakeFS({path: _host("workspace")})
    pool = [_block("voice", "global", "G voice", 10),
            _block("tone", "workspace", "W tone", 20)]

    out = write_surface(surface, pool, home=HOME, workspace=WS,
                        read_text=fs.read_text, write_text=fs.write_text)

    assert fs.writes == [path]
    assert fs.files[path] == out
    recs = ingest_region(out)
    assert [r.id for r in recs] == ["voice", "tone"]
    assert all(r.scope == "workspace" for r in recs)


def test_write_surface_refuses_a_non_catalog_surface():
    evil = Surface("evil", "global", ROOT_HOME, ".ssh/config")
    fs = FakeFS({})
    with pytest.raises(SurfaceError):
        write_surface(evil, [], home=HOME, workspace=WS,
                      read_text=fs.read_text, write_text=fs.write_text)
    assert fs.writes == []


def test_pool_for_is_the_public_authored_split():
    # The authored-split rule (which blocks render into a surface) is a public
    # seam: the R1 writer and the V2 verifier must resolve the same subset, so
    # neither reaches into a private. A workspace surface whose harness owns a
    # global sibling renders only the workspace-authored blocks (the globals
    # live in the sibling file).
    ws = Surface("claude-code", "workspace", ROOT_WORKSPACE, "CLAUDE.md")
    pool = [_block("voice", "global", "G", 10),
            _block("tone", "workspace", "W", 20)]
    assert [r.id for r in pool_for(ws, pool)] == ["tone"]
    # A lone workspace surface (no global sibling) renders the full merged set.
    soul = Surface("hermes", "workspace", ROOT_WORKSPACE, "SOUL.md")
    assert {r.id for r in pool_for(soul, pool)} == {"voice", "tone"}
    # A global surface renders the whole pool; layering resolves it.
    g = Surface("claude-code", "global", ROOT_HOME, ".claude/CLAUDE.md")
    assert {r.id for r in pool_for(g, pool)} == {"voice", "tone"}


def test_write_surface_does_not_write_when_the_region_is_unchanged():
    surface = Surface("claude-code", "workspace", ROOT_WORKSPACE, "CLAUDE.md")
    path = resolve_surface_path(surface, home=HOME, workspace=WS)
    fs = FakeFS({path: _host("workspace")})
    pool = [_block("tone", "workspace", "W tone", 20)]

    first = write_surface(surface, pool, home=HOME, workspace=WS,
                          read_text=fs.read_text, write_text=fs.write_text)
    second = write_surface(surface, pool, home=HOME, workspace=WS,
                           read_text=fs.read_text, write_text=fs.write_text)

    assert second == first
    assert fs.writes == [path]  # the second call was a no-op


def test_write_surfaces_refuses_a_path_through_a_link(tmp_path):
    """The allow-list check is lexical, so a junction or symlink on the way to
    a surface is refused before anything is read or written."""
    import os
    import sys

    from canon.registry import write_surfaces

    workspace, outside = tmp_path / "ws", tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    if sys.platform == "win32":
        import _winapi
        _winapi.CreateJunction(str(outside), str(workspace / ".github"))
    else:
        os.symlink(outside, workspace / ".github", target_is_directory=True)
    surface = next(s for s in SURFACE_CATALOG if s.harness == "copilot")
    with pytest.raises(SurfaceError, match="link"):
        write_surfaces([], home=str(tmp_path / "h"), workspace=str(workspace),
                       read_text=lambda p: None, write_text=lambda p, t: None,
                       surfaces=(surface,))
