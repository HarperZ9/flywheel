"""The LSP bridge must speak real framing and fail honestly: a scripted
server answers definition and hover through the full stack, a dead command
is a named error, and a bad method never reaches the wire."""

import sys
from pathlib import Path

from harness.lsp_bridge import lsp_query

FAKE = [sys.executable, str(Path(__file__).parent / "fake_lsp_server.py")]


def test_definition_roundtrip_through_real_framing(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = 1\n", encoding="utf-8")
    out = lsp_query(FAKE, str(tmp_path), str(f), "x = 1\n", "python",
                    "definition", 0, 0)
    assert out.get("error") is None, out
    loc = out["result"][0]
    assert loc["range"]["start"]["line"] == 2
    assert loc["uri"].endswith("a.py")


def test_hover_roundtrip(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = 1\n", encoding="utf-8")
    out = lsp_query(FAKE, str(tmp_path), str(f), "x = 1\n", "python",
                    "hover", 0, 0)
    assert out["result"]["contents"]["value"] == "fake hover"


def test_dead_command_is_a_named_error(tmp_path):
    out = lsp_query(["definitely-not-a-language-server-xyz"], str(tmp_path),
                    str(tmp_path / "a.py"), "", "python", "definition", 0, 0)
    assert "error" in out


def test_bad_method_and_bad_root_are_refused(tmp_path):
    out = lsp_query(FAKE, str(tmp_path), str(tmp_path / "a.py"), "", "python",
                    "rename", 0, 0)
    assert "error" in out
    out = lsp_query(FAKE, str(tmp_path / "nope"), "a.py", "", "python",
                    "definition", 0, 0)
    assert "error" in out
