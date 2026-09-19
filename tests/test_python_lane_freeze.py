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


def test_bundled_python_lanes_excludes_relay_and_canon():
    lanes = bundled_python_lanes(REPO)
    assert "relay" not in lanes and "canon" not in lanes
    # the eight staged-source lanes the freeze bundles through the helper
    assert lanes == ["accountable-surface", "chorus", "crucible", "forum",
                     "gather", "index", "mneme", "plexus"]


def test_bundled_python_lanes_exclusion_is_configurable():
    assert "canon" in bundled_python_lanes(REPO, exclude=("relay",))
