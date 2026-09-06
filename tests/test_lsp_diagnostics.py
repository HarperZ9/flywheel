"""Diagnostics and references must be real and bounded: the fake server
publishes a diagnostic for a broken buffer and none for a clean one, the
fence makes both visible, and references come back as locations.

Two of these are about the count rather than the messages. A server that only
answers when asked has to be asked, or this route reports zero for a file it
never looked at, and a server that says nothing has to read as unknown rather
than as a clean file. Both are the same bug from opposite sides.
"""

import sys
from pathlib import Path

from harness.lsp_diagnostics import lsp_diagnostics, lsp_references

FAKE = [sys.executable, str(Path(__file__).parent / "fake_lsp_server.py")]


def test_diagnostics_published_for_broken_buffer(tmp_path):
    f = tmp_path / "bad.py"
    f.write_text("broken = 1\n", encoding="utf-8")
    out = lsp_diagnostics(FAKE, str(tmp_path), str(f), "broken = 1\n",
                          "python")
    assert out.get("error") is None, out
    assert out["n"] == 1
    assert out["diagnostics"][0]["message"] == "fake: broken symbol"
    assert "never invented" in out["note"]


def test_clean_buffer_reads_empty_not_invented(tmp_path):
    f = tmp_path / "ok.py"
    f.write_text("x = 1\n", encoding="utf-8")
    out = lsp_diagnostics(FAKE, str(tmp_path), str(f), "x = 1\n", "python")
    assert out["n"] == 0
    assert out["diagnostics"] == []


def test_a_pull_only_server_is_asked_rather_than_fenced(tmp_path):
    # What a real ruff server does. It advertises a diagnostic provider, never
    # pushes, and the fence-only version of this route answered n=0 for a file
    # with problems in it, which a caller reads as clean.
    f = tmp_path / "bad.py"
    f.write_text("broken = 1\n", encoding="utf-8")
    out = lsp_diagnostics(FAKE + ["--pull"], str(tmp_path), str(f),
                          "broken = 1\n", "python")
    assert out.get("error") is None, out
    assert out["model"] == "diagnostic"
    assert out["n"] == 1
    assert out["diagnostics"][0]["message"] == "fake: broken symbol"


def test_a_server_that_said_nothing_reads_unknown_not_zero(tmp_path):
    # The false-success control. A count of zero here would be a count of a set
    # nobody produced, and this route's whole promise is that it does not
    # invent one.
    f = tmp_path / "quiet.py"
    f.write_text("broken = 1\n", encoding="utf-8")
    out = lsp_diagnostics(FAKE + ["--never-publish"], str(tmp_path), str(f),
                          "broken = 1\n", "python")
    assert out.get("error") is None, out
    assert out["published"] is False
    assert out["n"] is None


def test_references_roundtrip(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("x = 1\n", encoding="utf-8")
    out = lsp_references(FAKE, str(tmp_path), str(f), "x = 1\n", "python",
                         0, 0)
    assert out.get("error") is None, out
    locs = out["result"]
    assert len(locs) == 2
    assert locs[0]["range"]["start"]["line"] == 1
    assert locs[1]["range"]["start"]["line"] == 4


def test_dead_command_is_a_named_error(tmp_path):
    out = lsp_diagnostics(["no-such-server-xyz"], str(tmp_path),
                          str(tmp_path / "a.py"), "", "python")
    assert "error" in out
