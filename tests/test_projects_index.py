"""Projects registry and index bridge must be honest: a project root must
exist, the roster reflects live existence, and the index bridge names a
missing engine or bad root rather than fabricating a map."""

import pytest

from harness import index_bridge, projects


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "home"))


def test_add_list_remove_project(tmp_path):
    proj = tmp_path / "myrepo"
    proj.mkdir()
    (proj / "pyproject.toml").write_text("", encoding="utf-8")
    out = projects.add_project(str(proj))
    assert out["added"] == "myrepo"
    roster = projects.project_roster()
    row = next(p for p in roster["projects"] if p["name"] == "myrepo")
    assert row["exists"] is True
    assert row["kind"] == "python"
    # Duplicate refused.
    assert "error" in projects.add_project(str(proj))
    # Remove.
    assert projects.remove_project(str(proj))["removed"]
    assert projects.project_roster()["n"] == 0


def test_missing_root_refused(tmp_path):
    assert "error" in projects.add_project(str(tmp_path / "nope"))
    assert "error" in projects.add_project("")


def test_index_bridge_refuses_bad_root_and_unknown_view(tmp_path):
    proj = tmp_path / "r"
    proj.mkdir()
    assert "error" in index_bridge.index_view(str(tmp_path / "nope"), "map")
    assert "error" in index_bridge.index_view(str(proj), "bogus")


def test_index_summary_is_partial_not_crash_when_engine_absent(
        tmp_path, monkeypatch):
    proj = tmp_path / "r"
    proj.mkdir()
    # Force the "engine absent" path deterministically.
    monkeypatch.setattr(index_bridge, "_index_argv", lambda: None)
    summary = index_bridge.index_summary(str(proj))
    assert summary["schema"] == "flywheel.index-summary/v1"
    assert "map" in summary["errors"] and "graph" in summary["errors"]
