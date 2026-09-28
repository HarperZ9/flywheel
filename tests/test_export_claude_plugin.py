"""The export that makes plugins/flywheel-verify the root of its own repository.

The directory cannot validate the plugin from this repository: it holds more than
10,000 files and folders, and its root .gitattributes rewrites line endings. So a
listing is built from an exported tree. These tests hold the export to the file
rules, and the controls break each rule once to show the check catches it.
Passing them does not predict the portal's result, which runs more checks.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from harness import check_mcp_bundle as cb
from scripts import export_claude_plugin as ex

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "flywheel-verify"


def _source_files() -> list[str]:
    return sorted(p.relative_to(PLUGIN).as_posix() for p in PLUGIN.rglob("*") if p.is_file())


def test_the_plugin_folder_passes_the_rule_check():
    assert ex.layout_problems(PLUGIN) == []


def test_the_export_is_a_root_plugin_with_its_own_marketplace(tmp_path):
    out = tmp_path / "repo"
    written = ex.export(out)
    assert written == sorted(_source_files() + [".claude-plugin/marketplace.json"])
    for rel in _source_files():
        assert (out / rel).read_bytes() == (PLUGIN / rel).read_bytes(), rel
    manifest = json.loads((out / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    market = json.loads((out / ".claude-plugin" / "marketplace.json").read_text(
        encoding="utf-8"))
    assert market["name"] == manifest["name"] == "flywheel-verify"
    assert market["plugins"] == [{"name": "flywheel-verify", "source": "./",
                                  "description": manifest["description"]}]
    assert ex.layout_problems(out) == []
    # The copied sample bundle still verifies, so no byte changed on the way.
    result = cb.verify_bundle_tool({"path": "examples/bundle"}, roots=[out])
    assert result["verdict"] == "MATCH"


def test_the_export_refuses_a_folder_that_already_holds_files(tmp_path):
    (tmp_path / "keep.txt").write_text("kept", encoding="utf-8")
    with pytest.raises(ex.ExportError, match="not empty"):
        ex.export(tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == ["keep.txt"]


def test_the_command_line_reports_a_refusal(tmp_path, capsys):
    (tmp_path / "keep.txt").write_text("kept", encoding="utf-8")
    assert ex.main(["--out", str(tmp_path)]) == 1
    assert "export refused" in capsys.readouterr().err


def _minimal(root: Path) -> Path:
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text('{"name": "demo"}', encoding="utf-8")
    (root / "README.md").write_text("demo", encoding="utf-8")
    (root / "LICENSE").write_text("demo", encoding="utf-8")
    return root


def test_the_rule_check_passes_a_minimal_plugin(tmp_path):
    assert ex.layout_problems(_minimal(tmp_path)) == []


def _attrs(line: str):
    return lambda root: (root / ".gitattributes").write_text(line + "\n", encoding="utf-8")


BREAKS = {
    "top-level bin": (lambda root: (root / "bin").mkdir(), "bin must not be"),
    "CLAUDE.md": (lambda root: (root / "CLAUDE.md").write_text("x", encoding="utf-8"),
                  "CLAUDE.md must not be"),
    "no README": (lambda root: (root / "README.md").unlink(), "README.md is missing"),
    "no manifest": (lambda root: (root / ".claude-plugin" / "plugin.json").unlink(),
                    "plugin.json is missing"),
    "large text": (lambda root: (root / "big.txt").write_bytes(b"a" * ex.MAX_TEXT_BYTES),
                   "over the text-file limit"),
    "binary": (lambda root: (root / "tool.exe").write_bytes(b"MZ\x90\x00\xff\xfe"),
               "not UTF-8"),
    "OS file": (lambda root: (root / "Thumbs.db").write_bytes(b""), "operating-system file"),
    "eol rule": (_attrs("* text eol=lf"), "does more than turn conversion off"),
    "LFS filter": (_attrs("*.bin filter=lfs diff=lfs merge=lfs -text"),
                   "does more than turn conversion off"),
    "export-ignore": (_attrs("docs export-ignore"), "does more than turn conversion off"),
}


@pytest.mark.parametrize("name", sorted(BREAKS))
def test_the_rule_check_catches_each_break(tmp_path, name):
    root = _minimal(tmp_path)
    make, expected = BREAKS[name]
    make(root)
    problems = ex.layout_problems(root)
    assert any(expected in p for p in problems), problems


def test_the_rule_check_counts_files(tmp_path, monkeypatch):
    root = _minimal(tmp_path)
    monkeypatch.setattr(ex, "MAX_FILES", 2)
    assert any("more than 2" in p for p in ex.layout_problems(root))


@pytest.mark.parametrize("rel,expected", [
    ("docs/con.md", "reserved device name"), ("LPT1.txt", "reserved device name"),
    ("a:b.md", "invalid on Windows"), ("notes.", "invalid on Windows"),
    ("notes ", "invalid on Windows"), ("x/__MACOSX/y", "operating-system file"),
])
def test_names_windows_or_macos_cannot_hold_are_caught(rel, expected):
    # Checked on the name alone: a Windows host cannot create most of these.
    assert any(expected in p for p in ex._name_problems(Path(rel)))


def test_a_case_only_duplicate_is_caught(tmp_path):
    root = _minimal(tmp_path)
    (root / "Notes.md").write_text("a", encoding="utf-8")
    if (root / "notes.md").exists():
        pytest.skip("this file system ignores case, so it cannot hold both names")
    (root / "notes.md").write_text("b", encoding="utf-8")
    assert any("only by case" in p for p in ex.layout_problems(root))


def test_a_symlink_is_caught(tmp_path):
    root = _minimal(tmp_path)
    try:
        os.symlink(root / "README.md", root / "linked.md")
    except (OSError, NotImplementedError):
        pytest.skip("this host cannot create a symlink")
    assert any("symbolic link" in p for p in ex.layout_problems(root))
