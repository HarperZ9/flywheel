"""Import adapters: a stranger's harness config becomes a Flywheel project
manifest in one step, and the migration itself is a verifiable artifact —
every source content-hashed, every mapping named, everything unmappable
DROPPED with a reason instead of silently lost. Codex ships the migration;
Flywheel ships the migration plus the manifest."""

import json

from harness.import_adapters import SCHEMA, import_config


def _foreign(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# Project rules\nAlways run tests.",
                                        encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("Use small diffs.", encoding="utf-8")
    (tmp_path / ".cursorrules").write_text("prefer functional style",
                                           encoding="utf-8")
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text(json.dumps({
        "mcpServers": {"docs": {"command": "docs-mcp", "args": ["--stdio"]}},
        "hooks": {"PostToolUse": [{"command": "lint.sh"}]},
    }), encoding="utf-8")
    return tmp_path


def test_foreign_configs_map_with_hashes_and_reasons(tmp_path):
    doc = import_config(_foreign(tmp_path))
    assert doc["schema"] == SCHEMA
    by_source = {m["source"]: m for m in doc["mappings"]}
    assert by_source["CLAUDE.md"]["status"] == "mapped"
    assert by_source["CLAUDE.md"]["mapped_to"] == "instructions"
    assert len(by_source["CLAUDE.md"]["sha256"]) == 64
    assert by_source[".cursorrules"]["status"] == "mapped"
    assert by_source[".claude/settings.json"]["status"] == "partial"
    # MCP servers map; hooks do not (yet) — dropped with a reason, not lost.
    assert doc["profile"]["mcp_servers"]["docs"]["command"] == "docs-mcp"
    assert any("hooks" in d["reason"] for d in doc["dropped"])
    # The merged instructions carry every mapped text source.
    assert "Always run tests." in doc["profile"]["instructions"]
    assert "Use small diffs." in doc["profile"]["instructions"]
    assert "functional style" in doc["profile"]["instructions"]


def test_empty_directory_is_an_honest_null(tmp_path):
    doc = import_config(tmp_path)
    assert doc["mappings"] == []
    assert "nothing to import" in doc["note"]


def test_the_manifest_is_deterministic(tmp_path):
    _foreign(tmp_path)
    a = import_config(tmp_path)
    b = import_config(tmp_path)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
