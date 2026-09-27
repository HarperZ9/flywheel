"""The index 2.14.0 pin.

The 1.1.0 branch bundled index at 71c26eab, one commit past the v2.13.0 tag, and
disclosed it. index-graph 2.14.0 contains that commit, so the row pins the v2.14.0
tag and the Windows app, a pip install and CI get one release. 2.14.0 adds one MCP
tool, ``index.route``: it resolves ``root`` and each entry of ``paths`` (an absolute
entry as given, a relative one under ``root``), rejects an entry outside ``root``,
builds a context envelope over the named repositories and returns a route receipt.
It writes no file of its own; its per-repository graph cache goes where
``INDEX_GRAPH_REPO_CACHE_DIR`` points, which the engine sets inside the lane folder.
So the policy lists it as a T1 read with ``root`` a path argument and ``paths`` a
tree argument: index resolves each entry before it checks containment, so a network
spelling would reach its share first.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness import lane_tool_policy as policy
from harness import path_identity
from harness.lane_tier_gate import argument_refusal
from harness.lane_workdir import lane_state_defaults
from harness.lanes_registry import LANES

ROOT = Path(__file__).resolve().parents[1]
ROWS = {json.loads(line)["lane"]: json.loads(line) for line in (
    ROOT / "packaging" / "python-lane-payloads.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()}
VERSION, TAG, COMMIT = "2.14.0", "v2.14.0", "665ea7e24055266a9f3c26c5c84f0f3555b8234c"
NEW_TOOL = "index.route"


def _text(*parts: str) -> str:
    return " ".join(ROOT.joinpath(*parts).read_text(encoding="utf-8").split())


def test_registry_and_row_carry_the_pin():
    row = ROWS["index"]
    assert LANES["index"].version == VERSION
    assert (row["owner_tag"], row["owner_describe"], row["owner_commit"]) == (TAG, TAG, COMMIT)
    assert row["flywheel_registry_expected_version"] == VERSION
    assert row["owner_project"]["version"] == VERSION
    assert row["owner_project"]["imported_version"] == VERSION
    assert row["owner_project"]["license"] == {"text": "FSL-1.1-MIT"}
    assert row["component_descriptor"]["version"] == VERSION
    assert row["component_descriptor"]["source"]["commit"] == COMMIT
    assert "index_graph.route" in row["hidden_imports"]


def test_the_new_tool_has_a_reviewed_row_in_the_rows_order():
    row = ROWS["index"]
    served = row["mcp"]["static_tool_names"]
    assert NEW_TOOL in served and len(served) == 23
    assert served.index(NEW_TOOL) == served.index("index_router") + 1
    assert list(policy.lane_policy("index")) == served
    entry = policy.tool_policy("index", NEW_TOOL)
    assert (entry.tier, entry.effect, entry.not_in_build) == ("T1", "read", "")
    assert entry.path_args == ("root",) and entry.tree_args == ("paths",)
    admitted = policy.admitted_tools("index")
    assert NEW_TOOL in admitted and len(admitted) == 22
    assert row["component_descriptor"]["allowed_tools"] == admitted
    assert row["mcp"]["allowed_tools_for_initial_admission"] == admitted


def test_the_graph_cache_the_reason_names_is_set_inside_the_lane_folder(tmp_path):
    folder = tmp_path / "home" / "lanes" / "index"
    defaults = lane_state_defaults("index", folder, {})
    assert Path(defaults["INDEX_GRAPH_REPO_CACHE_DIR"]).parent.parent == folder
    assert "INDEX_GRAPH_REPO_CACHE_DIR" in policy.tool_policy("index", NEW_TOOL).reason


@pytest.fixture()
def home(tmp_path):
    root = tmp_path / "home"
    (root / "state").mkdir(parents=True)
    (root / "state" / "secret.json").write_text("{}", encoding="utf-8")
    (root / "lanes" / "index").mkdir(parents=True)
    (tmp_path / "work" / "repo-a").mkdir(parents=True)
    return root


def _refused(home: Path, args: dict) -> bool:
    refusal = argument_refusal("index", NEW_TOOL, args, {"FLYWHEEL_HOME": str(home)})
    return bool(refusal) and refusal["reason"] == "argument_refused"


def test_an_ordinary_route_passes(home, tmp_path):
    work = tmp_path / "work"
    assert not _refused(home, {"root": str(work), "paths": ["repo-a"]})
    assert not _refused(home, {"root": str(work), "paths": [str(work / "repo-a"), "repo-b"]})


def test_a_path_entry_in_flywheel_state_is_refused(home, tmp_path):
    work = str(tmp_path / "work")
    assert _refused(home, {"root": work, "paths": ["repo-a", str(home / "state")]})
    assert _refused(home, {"root": work, "paths": [str(home / "state" / "secret.json")]})
    assert _refused(home, {"root": str(home / "state"), "paths": ["repo-a"]})


@pytest.mark.parametrize("share", ["\\\\host.invalid\\share\\repo", "//host.invalid/share/repo",
                                   "\\\\?\\C:\\repo"])
def test_a_network_or_device_path_entry_is_refused(home, tmp_path, monkeypatch, share):
    monkeypatch.setattr(path_identity, "_WINDOWS", True)
    assert _refused(home, {"root": str(tmp_path / "work"), "paths": ["repo-a", share]})


def test_control_without_the_tree_argument_the_share_reaches_index(home, tmp_path,
                                                                   monkeypatch):
    """Control: the refusal above comes from ``paths`` being a tree argument."""
    import dataclasses
    monkeypatch.setattr(path_identity, "_WINDOWS", True)
    entry = policy.tool_policy("index", NEW_TOOL)
    bare = dataclasses.replace(entry, tree_args=())
    monkeypatch.setitem(policy.LANE_TOOL_POLICY["index"], NEW_TOOL, bare)
    assert not _refused(home, {"root": str(tmp_path / "work"),
                               "paths": ["\\\\host.invalid\\share\\repo"]})


def test_the_notice_names_the_tag_and_drops_the_describe():
    text = (ROOT / "desktop" / "release" / "THIRD-PARTY-NOTICES.txt").read_text(
        encoding="utf-8")
    assert f"index-graph {VERSION} (lane index), tag {TAG} @ {COMMIT[:12]}, FSL-1.1-MIT" in text
    assert "v2.13.0-1-g71c26ea" not in text
    assert "index-graph 2.13.0 (lane index)" not in text


def test_the_notes_name_the_release_and_drop_the_bundled_commit_limit():
    notes = _text("project-docs", "drafts", "RELEASE-NOTES-next.md")
    updates = notes.split("**Lane updates.**", 1)[1].split("- **", 1)[0]
    assert f"index {VERSION}" in updates and f"`{NEW_TOOL}`" in updates
    assert "no index release contains" not in notes
    assert "2.13.0 plus one later commit" not in notes


def test_the_feature_page_lists_the_pinned_tools():
    page = _text("docs", "features", "index.md")
    assert "the 23 the payload row lists" in page and "the 22 the payload row lists" not in page
    assert f"`index_router`, `{NEW_TOOL}`, `index_internals`" in page
    assert "18 tool definitions" not in page
