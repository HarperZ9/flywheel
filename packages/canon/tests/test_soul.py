"""test_soul.py -- R2 Module 5: the SOUL.md surface.

SOUL.md is the fourth confirmed instruction surface (harness "hermes"). It is a
workspace-scope, lone-file surface: no global sibling in the catalog, so under
the authored-split rule it renders the full merged block set, exactly like
Codex's AGENTS.md. It reuses the R0 block-region grammar byte-for-byte -- the
same `<!-- canon:begin ... -->` region a CLAUDE.md carries, with no SOUL-specific
banner or header (an honest null, D-36). The global SOUL.md path convention is
not yet pinned, so only the workspace surface is cataloged here.

These tests inject fake roots for the same reason the R1 tests do: no real path
reaches the repo.
"""
from __future__ import annotations

import os

import pytest

from canon.registry import (
    ROOT_WORKSPACE,
    SURFACE_CATALOG,
    Surface,
    is_write_allowed,
    resolve_surface_path,
    write_surface,
    write_surfaces,
)
from canon.schema import KIND_PERSONALITY_BLOCK, Provenance, Record
from canon.surface import SurfaceError
from canon.textblock import extract_region, ingest_region

HOME = os.path.join("fake", "home")
WS = os.path.join("fake", "ws")

SOUL_WS = Surface("hermes", "workspace", ROOT_WORKSPACE, "SOUL.md")
AGENTS_WS = Surface("codex", "workspace", ROOT_WORKSPACE, "AGENTS.md")


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


# 38
def test_catalog_includes_the_soul_surface():
    coords = {(s.harness, s.scope, s.root, s.relative_path)
              for s in SURFACE_CATALOG}
    assert ("hermes", "workspace", ROOT_WORKSPACE, "SOUL.md") in coords


# 39
def test_write_surface_writes_soul_through_the_allow_list():
    path = resolve_surface_path(SOUL_WS, home=HOME, workspace=WS)
    fs = FakeFS({path: _host("workspace")})

    out = write_surface(SOUL_WS, _pool(), home=HOME, workspace=WS,
                        read_text=fs.read_text, write_text=fs.write_text)

    assert fs.writes == [path]
    assert fs.files[path] == out
    recs = ingest_region(out)
    assert all(r.scope == "workspace" for r in recs)


# 40
def test_soul_is_a_lone_workspace_surface_merged_set():
    path = resolve_surface_path(SOUL_WS, home=HOME, workspace=WS)
    fs = FakeFS({path: _host("workspace")})
    out = write_surface(SOUL_WS, _pool(), home=HOME, workspace=WS,
                        read_text=fs.read_text, write_text=fs.write_text)
    recs = ingest_region(out)
    # no global sibling for "hermes" -> the lone file is self-sufficient: the
    # non-overridden global "mission" is folded in, and "voice" is the workspace
    # override, all projected to the workspace scope.
    assert [(r.id, r.data["body"]) for r in recs] == [
        ("mission", "G mission"), ("tone", "W tone"), ("voice", "W voice")]


# 41
def test_soul_path_allow_listed_and_neighbors_refused():
    soul = resolve_surface_path(SOUL_WS, home=HOME, workspace=WS)
    assert is_write_allowed(soul, home=HOME, workspace=WS)
    # a same-stem neighbor and a home-dir secret are not the cataloged surface
    assert not is_write_allowed(
        os.path.join(WS, "SOUL.local.md"), home=HOME, workspace=WS)
    assert not is_write_allowed(
        os.path.join(HOME, "SOUL.md"), home=HOME, workspace=WS)


# 42
def test_soul_region_grammar_matches_agents_no_banner():
    # SOUL and AGENTS are both lone workspace surfaces: with the same pool the
    # rendered region interiors are byte-identical. That proves SOUL reuses the
    # R0 block grammar with no SOUL-specific banner or header (honest null D-36).
    soul_path = resolve_surface_path(SOUL_WS, home=HOME, workspace=WS)
    agents_path = resolve_surface_path(AGENTS_WS, home=HOME, workspace=WS)
    fs = FakeFS({soul_path: _host("workspace"), agents_path: _host("workspace")})
    results = write_surfaces(
        _pool(), home=HOME, workspace=WS,
        read_text=fs.read_text, write_text=fs.write_text,
        surfaces=(SOUL_WS, AGENTS_WS))
    assert {r.status for r in results} == {"written"}
    soul_inner = extract_region(fs.files[soul_path]).inner
    agents_inner = extract_region(fs.files[agents_path]).inner
    assert soul_inner == agents_inner
    # and the interior is the bare block grammar: it opens on a block marker,
    # with no generated-by / title banner line ahead of it.
    assert soul_inner.lstrip().startswith("<!-- canon:block")
