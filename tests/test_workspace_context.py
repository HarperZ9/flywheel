"""Tests for deterministic workspace context loading (harness/workspace_context.py)."""
from __future__ import annotations

from harness.workspace_context import discover_context_files, load_workspace_context


def test_discovers_and_loads_user_and_workspace_context_with_hashes(tmp_path):
    fw_home = tmp_path / "fw_home"
    (fw_home / "memory").mkdir(parents=True)
    (fw_home / "instructions.md").write_text("Global rule: verify.", encoding="utf-8")
    (fw_home / "memory" / "MEMORY.md").write_text("- Memory index entry", encoding="utf-8")

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "PROJECTS.md").write_text("# Projects", encoding="utf-8")
    (ws / "AGENTS.md").write_text("# Agents", encoding="utf-8")

    files = discover_context_files(ws, flywheel_home=fw_home)
    kinds = [f["kind"] for f in files]
    assert kinds == [
        "user-instructions",
        "user-memory",
        "workspace-projects",
        "workspace-instructions",
    ]

    bundle = load_workspace_context(ws, flywheel_home=fw_home, max_chars=2000)
    assert bundle["schema"] == "flywheel.workspace-context/v1"
    assert bundle["source_count"] == 4
    assert all(len(s["sha256"]) == 64 for s in bundle["sources"])
    assert "Global rule: verify." in bundle["context_text"]
    assert "# Projects" in bundle["context_text"]


def test_respects_max_chars_budget(tmp_path):
    fw_home = tmp_path / "fw_home"
    fw_home.mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "AGENTS.md").write_text("x" * 500, encoding="utf-8")

    bundle = load_workspace_context(ws, flywheel_home=fw_home, max_chars=100)
    assert bundle["sources"][0]["truncated"] is True
    assert bundle["sources"][0]["included_chars"] == 100
