"""Explicit source runtime for grant tests unrelated to package availability."""
import pytest

from harness import lanes


@pytest.fixture(autouse=True)
def relay_source_runtime(monkeypatch, tmp_path):
    source = tmp_path / "relay-source"
    (source / "src" / "relay").mkdir(parents=True)
    version = lanes.LANES["relay"].version
    (source / "pyproject.toml").write_text(
        f'[project]\nversion="{version}"\n', encoding="utf-8")
    original = lanes.resolve_source_repo
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: (
        source if lane.name == "relay" else original(lane)))
    monkeypatch.setattr(lanes, "read_registry", lambda: {})
    monkeypatch.setattr(lanes, "_frozen", lambda: False)
