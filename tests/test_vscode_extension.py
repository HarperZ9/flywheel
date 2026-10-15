"""Falsifiers for the VS Code extension: its manifest, its .vsix, and what it types."""
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "integrations" / "vscode"


def test_manifest_commands_match_what_the_extension_registers():
    pkg = json.loads((EXT / "package.json").read_text(encoding="utf-8"))
    declared = {c["command"] for c in pkg["contributes"]["commands"]}
    source = (EXT / "extension.js").read_text(encoding="utf-8")
    for cmd in declared:
        assert f"reg('{cmd}'" in source, cmd
    assert "dependencies" not in pkg                       # ships with no dependencies


def test_vsix_holds_the_manifest_and_the_extension(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("vsix", ROOT / "scripts" / "build_vscode_vsix.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = mod.build(tmp_path / "x.vsix")
    names = zipfile.ZipFile(out).namelist()
    assert names[:2] == ["[Content_Types].xml", "extension.vsixmanifest"]
    assert {"extension/package.json", "extension/extension.js", "extension/LICENSE.txt"} <= set(names)
    again = mod.build(tmp_path / "y.vsix")
    assert out.read_bytes() == again.read_bytes()          # same source, same bytes


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_extension_starts_a_session_and_sends_a_mention():
    out = subprocess.run(["node", str(EXT / "test" / "mock_run.js")], capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert "flywheel.askSelection" in result["registered"]
    assert result["sent"][0] == "flywheel code --mode edit --backend claude"
    assert result["sent"][1] == 'what does this do? @src/a b.py (lines 10 to 20)'
    assert result["created"] == 1                           # the second command reused the terminal
