"""A PATH entry inside the folder a child works in never answers for its program.

The caller runs in one folder and the child in another: git with ``-C``, Lean
beside a proof file, manim in its output folder, a server in its workspace. A
PATH entry naming a folder inside the child's folder (a repository's ``bin``, a
workspace's ``.venv``) holds a plant under every program's name. subprocess is
replaced by a recorder, so nothing starts; every recorded argv must name the
copy in the absolute PATH folder that follows. On 1.1.1 before this check, the
git ``-C`` sites, the proof runner and the manim render found the plant.
"""
from __future__ import annotations

import os

import pytest

from test_spawn_site_vectors import layout, recorder  # noqa: F401  (fixtures)
from test_spawn_sites_resolve import NAMES, SITES, _exe, same

WINDOWS = os.name == "nt"


#: Sites whose child works in the folder the test hands them: git -C, a cwd, a
#: workspace. The caller's own folder is elsewhere, so only the child's folder
#: is at stake.
CHILD_FOLDER_SITES = (
    "boot git head", "continuation preview git", "local_git", "routing collection git head",
    "session summary git", "studio engine git head", "workspace git identity",
    "worktree preflight", "trace bench replay git", "proof run", "mcp launch spec",
    "stdio protocol server", "debug adapter launch", "command authority",
    "verified bench gate", "buildc receipt verify", "manim render")


@pytest.mark.parametrize("site", CHILD_FOLDER_SITES)
def test_an_absolute_path_entry_inside_the_childs_folder_is_skipped(
        site, layout, recorder, monkeypatch):  # noqa: F811  (imported fixtures)
    """The caller runs in another folder; a PATH entry names a folder inside the
    one the child works in (a repository's bin, a workspace's .venv)."""
    work, bin_, tmp = layout
    elsewhere = tmp / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    for name in NAMES:
        _exe(work / "tools", name)
        _exe(bin_, name)
    monkeypatch.setenv("PATH", os.pathsep.join((str(work / "tools"), str(bin_))))
    name, call = SITES[site]
    seen = recorder()
    try:
        call(work)
    except Exception:
        pass
    assert seen, f"{site} never reached subprocess"
    for argv in seen:
        expected = bin_ / (f"{name}.exe" if WINDOWS else name)
        assert same(argv[0], expected), f"{site} started {argv[0]!r}"
