"""The engine refuses a path argument that names a reserved Windows device.

Windows opens a device, not a file, for a path component whose base name is
CON, PRN, AUX, NUL, CONIN$, CONOUT$, COM1-COM9 or LPT1-LPT9 (and the superscript
1, 2 and 3 forms), in any folder and with any extension. The engine's guard
refused UNC and device-namespace spellings but passed ``C:\\docs\\CON.md`` on
every lane; only gather 1.9.1 refused it on its own. A T1 read tool pointed at a
serial or console device can block until the tool's timeout. The guard now reads
a reserved name the way gather's ``localpath._reserved`` does and answers
``argument_refused`` before any child spawns.
"""
from __future__ import annotations

import os

import pytest

from harness.lane_tier_gate import argument_refusal
from harness.path_identity import reserved_device_name

BS = chr(92)
# One path-argument tool per lane that takes a path (the first in each table).
TARGETS = [("gather", "gather.docs", "path"), ("crucible", "crucible.assess", "thesis"),
           ("chorus", "chorus.run", "corpus"), ("index", "index.map", "root"),
           ("plexus", "plexus_discover", "dir"), ("canon", "canon.validate", "record"),
           ("mneme", "mneme.origin_recheck", "allowed_root"),
           ("local-model", "local_agent_run", "root"),
           ("accountable-surface", "accountable-surface.perceive", "subject"),
           ("learn", "learn_dry_run", "workflowPath")]
RESERVED = ["C:" + BS + "docs" + BS + "CON.md", "C:" + BS + "x" + BS + "NUL",
            "C:" + BS + "x" + BS + "COM1", "C:" + BS + "x" + BS + "CONIN$",
            "C:" + BS + "x" + BS + "conout$.txt", "C:" + BS + "x" + BS + "lpt\u00b2",
            "C:" + BS + "x" + BS + "AUX . .", "C:" + BS + "x" + BS + "com9:stream",
            "C:" + BS + "prn" + BS + "notes.md", "docs" + BS + "Nul.json"]
ORDINARY = ["C:" + BS + "docs" + BS + "CONTRIBUTING.md", "C:" + BS + "x" + BS + "COM0",
            "C:" + BS + "x" + BS + "LPT0.txt", "C:" + BS + "x" + BS + "console.md",
            "C:" + BS + "x" + BS + "nullable", "C:" + BS + "x" + BS + "auxiliary",
            "C:" + BS + "x" + BS + "com10"]


@pytest.fixture()
def environ(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    return {"FLYWHEEL_HOME": str(home)}


@pytest.mark.parametrize("lane,tool,arg", TARGETS, ids=lambda v: str(v))
@pytest.mark.parametrize("value", RESERVED)
def test_a_reserved_device_name_is_refused_on_every_lane(environ, lane, tool, arg, value):
    refused = argument_refusal(lane, tool, {arg: value}, environ)
    assert refused is not None, (lane, tool, value)
    assert (refused["code"], refused["reason"]) == ("LANE_TOOL_ERROR", "argument_refused")


@pytest.mark.parametrize("value", ORDINARY)
def test_an_ordinary_name_that_starts_like_a_device_passes(environ, value):
    for lane, tool, arg in TARGETS:
        assert argument_refusal(lane, tool, {arg: value}, environ) is None, (lane, value)


def test_the_rule_reads_windows_text_everywhere_and_posix_text_only_on_windows():
    assert reserved_device_name("C:" + BS + "docs" + BS + "CON.md", windows=False)
    assert reserved_device_name("docs" + BS + "con", windows=False)
    assert not reserved_device_name("/home/me/con.md", windows=False)
    assert reserved_device_name("/home/me/con.md", windows=True)
    assert reserved_device_name("CONIN$", windows=True)
    assert not reserved_device_name("CONIN$", windows=False)


@pytest.mark.skipif(os.name == "nt", reason="a POSIX file named con.md exists only off Windows")
def test_a_posix_file_named_like_a_device_passes_off_windows(environ):
    assert argument_refusal("gather", "gather.docs", {"path": "/srv/notes/con.md"},
                            environ) is None


def test_a_tree_argument_keeps_text_that_reads_like_a_device(environ):
    """gather.run's inline config also holds text that is not a path, such as a
    query; a reserved name there is left to gather, which refuses one in any
    path it opens. A UNC path in the tree is still refused by the engine."""
    config = {"sources": [{"kind": "arxiv", "query": "aux"}]}
    assert argument_refusal("gather", "gather.run", {"config": config}, environ) is None
    unc = {"sources": [{"kind": "docs", "path": BS + BS + "srv" + BS + "share"}]}
    refused = argument_refusal("gather", "gather.run", {"config": unc}, environ)
    assert refused is not None and refused["reason"] == "argument_refused"
