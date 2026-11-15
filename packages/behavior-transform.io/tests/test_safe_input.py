import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import json
import os
import pytest

from safe_input import _read_input, _archive_raw, main


def test_read_input_from_content():
    text = _read_input(from_path=None, content="hello", from_clipboard=False)
    assert text == "hello"


def test_read_input_from_file(tmp_path):
    f = tmp_path / "input.txt"
    f.write_text("file content")
    text = _read_input(from_path=f, content=None, from_clipboard=False)
    assert text == "file content"


def test_archive_raw(tmp_path):
    os.chdir(tmp_path)
    path = _archive_raw("test content")
    assert path.exists()
    assert path.read_text() == "test content"
    assert "prompts" in str(path)


def test_main_diff_only(capsys):
    rc = main(["--content", "clean text", "--diff-only", "--IO-off"])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert "substitutions" in parsed
    assert parsed["total"] == 0


def test_main_check_only_clean(capsys):
    rc = main(["--content", "clean text", "--check-only", "--IO-off"])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "OK"


def test_main_no_header(capsys):
    rc = main(["--content", "clean text", "--no-header", "--IO-off", "--no-archive"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "CALIBRATED" not in out
    assert "clean text" in out


def test_main_empty_input(capsys):
    rc = main(["--content", "   ", "--no-archive"])
    assert rc == 2


def test_main_io_off_passthrough(capsys):
    rc = main(["--content", "passthrough text", "--IO-off", "--no-archive"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "passthrough text" in out


def test_main_with_header(capsys):
    rc = main(["--content", "test text", "--IO-on", "--no-archive"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "CALIBRATED INPUT" in out or "test text" in out
