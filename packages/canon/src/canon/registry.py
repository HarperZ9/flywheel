"""registry.py -- R1: the write-surface allow-list.

The renderer may rewrite ONLY the managed instruction files named in the fixed
catalog below. Each Surface names a harness, a scope, the root it lives under
(the home directory or the workspace root), and its path relative to that root.

The absolute roots are injected at call time and never stored here, so this
public catalog carries no operator path: only the generic filename conventions
(`.claude/CLAUDE.md`, `CLAUDE.md`, `AGENTS.md`) live in source. A write is
allowed only if its resolved path is exactly one of the catalog surfaces under
the injected roots; anything else -- a secret file, a traversal escape, an
ad-hoc surface, or a path that runs through a symlink or junction -- is
refused before a byte is read or written.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from canon.path_policy import PathPolicyError, resolve_under_root
from canon.region import extract_region
from canon.schema import Record
from canon.surface import SurfaceError, apply_surface

ROOT_HOME = "home"
ROOT_WORKSPACE = "workspace"


@dataclass(frozen=True, slots=True)
class Surface:
    """One managed file canon is allowed to rewrite: (harness, scope) bound to a
    root-kind and a path relative to that root. Path-free of any absolute root."""

    harness: str
    scope: str
    root: str
    relative_path: str


# The confirmed instruction surfaces. SOUL.md (harness "hermes") is a lone
# workspace surface: no global sibling, so it renders the full merged set like
# AGENTS.md, and it reuses the R0 block-region grammar with no banner. W1 adds
# three more lone workspace surfaces, each chosen deliberately: GEMINI.md (Gemini
# CLI), .github/copilot-instructions.md (GitHub Copilot's repository-wide file),
# and one canon-owned Cursor rule, .cursor/rules/canon.mdc. canon writes that one
# rule file and no other file under .cursor/rules. What each of them cannot
# express (glob-scoped activation) is declared in workspace/target_fidelity.py.
# The global GEMINI.md and the GLOBAL SOUL.md are not pinned yet. The vault is
# not listed here: it is a whole-directory mirror with its own containment
# (vault_mirror.is_vault_write_allowed), not a single-file region-splice
# surface, so it is deliberately not a root-kind (D-35).
SURFACE_CATALOG: tuple[Surface, ...] = (
    Surface("claude-code", "global", ROOT_HOME, ".claude/CLAUDE.md"),
    Surface("claude-code", "workspace", ROOT_WORKSPACE, "CLAUDE.md"),
    Surface("codex", "workspace", ROOT_WORKSPACE, "AGENTS.md"),
    Surface("hermes", "workspace", ROOT_WORKSPACE, "SOUL.md"),
    Surface("gemini-cli", "workspace", ROOT_WORKSPACE, "GEMINI.md"),
    Surface("copilot", "workspace", ROOT_WORKSPACE, ".github/copilot-instructions.md"),
    Surface("cursor", "workspace", ROOT_WORKSPACE, ".cursor/rules/canon.mdc"),
)


def _root_dir(surface: Surface, *, home: str, workspace: str) -> str:
    return home if surface.root == ROOT_HOME else workspace


def resolve_surface_path(surface: Surface, *, home: str, workspace: str) -> str:
    """Join `surface` onto its injected root, normalized for the platform."""
    root = _root_dir(surface, home=home, workspace=workspace)
    return os.path.normpath(os.path.join(root, surface.relative_path))


def allowed_paths(*, home: str, workspace: str) -> set[str]:
    """Every catalog surface resolved under the injected roots."""
    return {resolve_surface_path(s, home=home, workspace=workspace)
            for s in SURFACE_CATALOG}


def is_write_allowed(path: str, *, home: str, workspace: str) -> bool:
    """True only if `path` normalizes to exactly one allow-listed surface. A
    case-insensitive filesystem folds case; a traversal escape collapses under
    normpath and simply fails to match."""
    target = os.path.normcase(os.path.normpath(path))
    allowed = {os.path.normcase(p)
               for p in allowed_paths(home=home, workspace=workspace)}
    return target in allowed


def assert_writable(path: str, *, home: str, workspace: str) -> None:
    """Raise SurfaceError unless `path` is an allow-listed surface."""
    if not is_write_allowed(path, home=home, workspace=workspace):
        raise SurfaceError(
            f"path is not an allow-listed canon surface: {path!r}")


def assert_no_link(path: str, root: str) -> None:
    """Raise SurfaceError when `path`, or a directory between it and `root`,
    is a symlink, junction or other reparse point. The allow-list check is
    lexical; a link would carry the write outside the root. Only the part below
    the root is checked, so a root that sits behind a link itself is fine. A
    root that does not exist on disk (injected IO in a test) has nothing to
    follow."""
    if not os.path.isdir(root):
        return
    real = os.path.realpath(root)
    try:
        resolve_under_root(os.path.join(real, os.path.relpath(path, root)), root=real,
                           reject_reparse=True)
    except PathPolicyError as exc:
        raise SurfaceError(f"path runs through a link: {exc}") from exc


def write_surface(surface: Surface, pool: list[Record], *, home: str,
                  workspace: str, read_text, write_text) -> str:
    """Render `pool` at `surface.scope` into `surface`'s file and write it back,
    only through an allow-listed surface and only when the region changes.

    Guards fail closed before any IO: a surface outside the catalog, or one that
    resolves outside the allow-listed paths, is refused. IO is injected so the
    guard is provable without touching the filesystem.
    """
    if surface not in SURFACE_CATALOG:
        raise SurfaceError(
            f"surface is not in the write allow-list: {surface!r}")
    path = resolve_surface_path(surface, home=home, workspace=workspace)
    assert_writable(path, home=home, workspace=workspace)
    assert_no_link(path, _root_dir(surface, home=home, workspace=workspace))
    host = read_text(path)
    new = apply_surface(host, pool, surface.scope)
    if new != host:
        write_text(path, new)
    return new


@dataclass(frozen=True, slots=True)
class SurfaceResult:
    """The outcome of rendering one surface: written, unchanged, off-limits
    (the host had no canon region and was left untouched), or missing (read_text
    returned None: the file does not exist, so there is nothing to opt in)."""

    surface: Surface
    path: str
    status: str
    content: str | None


def _has_global_surface(harness: str) -> bool:
    return any(s.harness == harness and s.scope == "global"
               for s in SURFACE_CATALOG)


def pool_for(surface: Surface, pool: list[Record]) -> list[Record]:
    """The block subset a surface renders under the authored-split rule.

    A global surface renders the pool (layering resolves it to the globals). A
    workspace surface renders only the workspace-authored blocks when the same
    harness also owns a global surface -- the globals live in that sibling file,
    so folding them in here would duplicate them where a harness reads both. A
    workspace surface with no global sibling renders the full merged set, so its
    lone file stays self-sufficient.

    Public so the R1 writer and the V2 verifier resolve one authored-split: the
    drift check and the writing gate render exactly what write_surfaces writes.
    """
    if surface.scope == "global":
        return pool
    if _has_global_surface(surface.harness):
        return [r for r in pool if r.scope == "workspace"]
    return pool


def write_surfaces(pool: list[Record], *, home: str, workspace: str,
                   read_text, write_text,
                   surfaces: tuple[Surface, ...] | None = None
                   ) -> list[SurfaceResult]:
    """Render every surface in `surfaces` (default: the whole catalog) from one
    pool, each by the authored-split rule. A host with no canon region is
    skipped and reported off-limits, never mutated; a surface whose region is
    present but mis-scoped fails closed through apply_surface. Only a changed
    region is written back.

    The batch is all-or-nothing. Every surface is planned first -- static guards
    (catalog membership, allow-listed path) and every per-host refusal
    (off-limits skip, mis-scope raise) resolve in this pass, before a single
    write. Only once the whole set plans clean are the changed regions committed,
    so a later surface's refusal never leaves an earlier one half-written. This
    covers canon's own refusals; a filesystem fault inside the commit pass (a
    write_text that fails after earlier files wrote) is not rolled back.
    """
    chosen = SURFACE_CATALOG if surfaces is None else surfaces
    planned: list[tuple[str, str]] = []
    results: list[SurfaceResult] = []
    for surface in chosen:
        if surface not in SURFACE_CATALOG:
            raise SurfaceError(
                f"surface is not in the write allow-list: {surface!r}")
        path = resolve_surface_path(surface, home=home, workspace=workspace)
        assert_writable(path, home=home, workspace=workspace)
        assert_no_link(path, _root_dir(surface, home=home, workspace=workspace))
        host = read_text(path)
        if host is None:
            results.append(SurfaceResult(surface, path, "missing", None))
            continue
        if not extract_region(host).present:
            results.append(SurfaceResult(surface, path, "off-limits", None))
            continue
        new = apply_surface(host, pool_for(surface, pool), surface.scope)
        if new != host:
            planned.append((path, new))
            results.append(SurfaceResult(surface, path, "written", new))
        else:
            results.append(SurfaceResult(surface, path, "unchanged", new))
    for path, content in planned:
        write_text(path, content)
    return results
