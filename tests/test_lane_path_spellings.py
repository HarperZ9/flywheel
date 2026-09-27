"""A path argument is checked where the lane reads it, however it is spelled.

The engine expanded "~" and stripped blanks before its home check. index 2.14.0
reads the text as given: ``Path(root).resolve()`` with no expanduser, so "~" is
a folder name under the lane folder (the child's working directory) and a
leading blank is part of a name. A root of ``~/../../../state`` expanded to a
folder outside the home and passed, while index read it from the lane folder
as the home's state and built its graph. Lanes that call expanduser read the
user's folder instead, so the engine now checks the value both as given and
stripped with "~" expanded, and either one reaching the state refuses the call.
"""
from __future__ import annotations

import pytest

from harness.lane_tier_gate import argument_refusal


@pytest.fixture()
def home(tmp_path, monkeypatch):
    root = tmp_path / "home"
    (root / "state").mkdir(parents=True)
    for lane in ("index", "gather"):
        (root / "lanes" / lane).mkdir(parents=True)
    user = tmp_path / "user"            # "~" expands here, outside the home
    user.mkdir()
    for name in ("USERPROFILE", "HOME"):
        monkeypatch.setenv(name, str(user))
    monkeypatch.setenv("FLYWHEEL_HOME", str(root))
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(tmp_path / "run"))
    return root


def _refused(lane: str, tool: str, args: dict) -> bool:
    refusal = argument_refusal(lane, tool, args)
    return bool(refusal) and refusal["reason"] == "argument_refused"


def test_a_tilde_root_is_checked_from_the_lane_folder_where_index_reads_it(home):
    # index reads <home>/lanes/index/~/../../../state, the home's state; expanded,
    # the same text names a folder above the user folder.
    assert _refused("index", "index_graph", {"root": "~/../../../state"})
    assert _refused("index", "index_graph", {"root": "~/../../.."})
    assert _refused("index", "index.map", {"root": "~/../../../state"})
    assert _refused("index", "index.route", {"root": "~/../../../state", "paths": ["repo"]})
    assert not _refused("index", "index_graph", {"root": "~/work"})
    assert not _refused("index", "index_graph", {"root": "~/.."})     # the lane's own folder


def test_an_expanded_tilde_into_the_home_is_still_refused(home):
    # gather expands "~"; read as given the text stays in the lane's own folder.
    assert _refused("gather", "gather.docs", {"path": "~/../home/state/x"})
    assert not _refused("gather", "gather.docs", {"path": "~/notes"})


def test_a_leading_blank_is_checked_as_index_reads_it(home):
    # Stripped, the text is a path at the top of the drive; as given, " " is a
    # folder name under the lane folder and the dots climb to the home's state.
    assert _refused("index", "index_graph", {"root": " /x/../../../../state"})
    assert not _refused("index", "index_graph", {"root": " /x"})
