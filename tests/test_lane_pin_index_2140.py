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
spelling would reach its share first. ``root`` is also the tree base: index reads a
relative entry under ``root``, so the engine checks it there as well as from the lane
folder, and a ``root`` that contains the home cannot name its state by a relative
entry that the absolute spelling of the same folder would not pass.
"""
from __future__ import annotations

import json
import re
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
VERSION, TAG, COMMIT = "2.15.0", "v2.15.0", "b2e4dcefff9d9d9a339e23d64c58bb4a5149ef92"
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
    assert entry.tree_base == "root"
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


def _refused(home: Path, args: dict, **env: str) -> bool:
    refusal = argument_refusal("index", NEW_TOOL, args, {"FLYWHEEL_HOME": str(home), **env})
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


def test_a_relative_entry_is_checked_under_root_where_index_reads_it(home, tmp_path):
    """index joins a relative entry to ``root``. Under a root that contains the
    home, the relative spelling of a state folder is refused like the absolute one."""
    parent = str(tmp_path)
    assert _refused(home, {"root": parent, "paths": [str(home / "state")]})   # control
    assert _refused(home, {"root": parent, "paths": ["home/state"]})
    assert _refused(home, {"root": parent, "paths": ["work/repo-a", "home/state/secret.json"]})
    assert _refused(home, {"root": parent, "paths": ["home/lanes/../state"]})
    # a relative root is read from the lane folder, the child's working directory
    assert _refused(home, {"root": "../../..", "paths": ["home/state"]})
    (tmp_path / "runs").mkdir()
    assert _refused(home, {"root": parent, "paths": ["runs"]},
                    FLYWHEEL_RUN_ROOT=str(tmp_path / "runs"))
    assert not _refused(home, {"root": parent, "paths": ["work/repo-a"]})
    assert not _refused(home, {"root": parent, "paths": ["home/lanes/index"]})


def test_control_without_the_tree_base_a_relative_entry_passes(home, tmp_path, monkeypatch):
    """Control: the refusal above comes from ``root`` being the tree base."""
    import dataclasses
    entry = policy.tool_policy("index", NEW_TOOL)
    monkeypatch.setitem(policy.LANE_TOOL_POLICY["index"], NEW_TOOL,
                        dataclasses.replace(entry, tree_base=""))
    assert not _refused(home, {"root": str(tmp_path), "paths": ["home/state"]})
    assert _refused(home, {"root": str(tmp_path), "paths": [str(home / "state")]})


def test_a_tree_base_must_be_a_path_argument_of_a_tool_with_a_tree_argument():
    import dataclasses
    entry = policy.tool_policy("index", NEW_TOOL)
    assert policy.validate_policy({"index": {NEW_TOOL: entry}}) == []
    for bad in (dataclasses.replace(entry, tree_base="paths"),
                dataclasses.replace(entry, tree_args=())):
        problems = policy.validate_policy({"index": {NEW_TOOL: bad}})
        assert any("a tree base must be a path argument" in p for p in problems), problems


def test_the_notice_names_the_tag_and_drops_the_describe():
    text = (ROOT / "desktop" / "release" / "THIRD-PARTY-NOTICES.txt").read_text(
        encoding="utf-8")
    assert f"index-graph {VERSION} (lane index), tag {TAG} @ {COMMIT[:12]}, FSL-1.1-MIT" in text
    assert "v2.13.0-1-g71c26ea" not in text
    assert "index-graph 2.13.0 (lane index)" not in text


def test_the_notes_name_the_release_and_drop_the_bundled_commit_limit():
    notes = _text("RELEASE-NOTES-1.1.0.md")
    updates = notes.split("**Lane updates.**", 1)[1].split("- **", 1)[0]
    assert "index 2.14.0" in updates and f"`{NEW_TOOL}`" in updates
    assert "no index release contains" not in notes
    assert "2.13.0 plus one later commit" not in notes


def test_the_known_issues_page_names_the_commit_the_1_0_x_apps_bundled():
    """The 1.0.3 and 1.0.4 rows pin 71c26eab while their notes name index 2.13.0;
    the notes' limit that said so left with the pin, so the 1.0.4 page carries it."""
    known = _text("RELEASE-NOTES-1.0.4-known-issues.md")
    assert "six statements about the installed Windows app" in known
    assert "bundled index 2.13.0 plus one later commit" in known
    assert "until 2.14.0, which Flywheel 1.1.0 pins" in known


def test_the_feature_page_lists_the_pinned_tools():
    page = _text("docs", "features", "index.md")
    assert "the 23 the payload row lists" in page and "the 22 the payload row lists" not in page
    assert f"`index_router`, `{NEW_TOOL}`, `index_internals`" in page
    assert "18 tool definitions" not in page


def test_the_feature_page_names_the_tools_the_pinned_index_caches():
    """The cache sentence names the tools the pinned mcp.py caches
    (``_CACHEABLE_TOOLS``), and the page cites no test count: the pinned
    README carries none."""
    index_graph = pytest.importorskip("index_graph")
    if index_graph.__version__ != VERSION:
        pytest.skip(f"index-graph {index_graph.__version__} installed, not {VERSION}")
    from index_graph.mcp import _CACHEABLE_TOOLS
    page = _text("docs", "features", "index.md")
    assert "tools cache their result" in page
    sentence = page.split("tools cache their result", 1)[1].split(". ", 1)[0]
    named = set(re.findall(r"`([^`]+)`", sentence)) - {"bounded_output"}
    assert named == set(_CACHEABLE_TOOLS)
    assert "index.map" not in sentence
    assert not re.search(r"\b\d+ tests\b", page)
