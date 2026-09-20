from pathlib import Path

from scripts.python_lane_freeze import (
    bundled_python_lanes, lane_hidden_imports)

REPO = Path(__file__).resolve().parents[1]


def _row(files):
    return {"component_descriptor": {"source": {"files": files}}}


def test_lane_hidden_imports_derives_every_package_module():
    row = _row([
        {"path": "src/index_graph/__init__.py"},
        {"path": "src/index_graph/mcp.py"},
        {"path": "src/index_graph/arch/__init__.py"},
        {"path": "src/index_graph/arch/build.py"},
        {"path": "src/index_graph/data.json"},   # non-py is skipped
        {"path": "README.md"},                     # outside src is skipped
    ])
    assert lane_hidden_imports(row) == [
        "index_graph",
        "index_graph.arch",
        "index_graph.arch.build",
        "index_graph.mcp",
    ]


def test_lane_hidden_imports_is_sorted_and_deduped():
    row = _row([{"path": "src/pkg/a.py"}, {"path": "src/pkg/a.py"},
                {"path": "src/pkg/__init__.py"}])
    assert lane_hidden_imports(row) == ["pkg", "pkg.a"]


def test_bundled_python_lanes_excludes_only_relay_by_default():
    lanes = bundled_python_lanes(REPO)
    assert "relay" not in lanes
    # Canon is bundled through the helper too, so its bundled-lane entrypoint
    # (canon.local_mcp) reaches the freeze; only relay (the submodule) is out.
    assert lanes == ["accountable-surface", "canon", "chorus", "crucible",
                     "forum", "gather", "index", "mneme", "plexus"]


def test_bundled_python_lanes_exclusion_is_configurable():
    assert "canon" not in bundled_python_lanes(REPO, exclude=("relay", "canon"))
