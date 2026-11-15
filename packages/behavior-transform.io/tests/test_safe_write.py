import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import json
import os
import pytest

from safe_write import _read_input, _atomic_write, _archive_pre_write, main


def test_read_input_from_content():
    text = _read_input(from_path=None, content="hello world")
    assert text == "hello world"


def test_read_input_from_file(tmp_path):
    f = tmp_path / "src.txt"
    f.write_text("file content")
    text = _read_input(from_path=f, content=None)
    assert text == "file content"


def test_atomic_write_creates_file(tmp_path):
    dest = tmp_path / "output.txt"
    _atomic_write(dest, "written content", append=False)
    assert dest.read_text() == "written content"


def test_atomic_write_creates_parents(tmp_path):
    dest = tmp_path / "deep" / "nested" / "file.txt"
    _atomic_write(dest, "nested", append=False)
    assert dest.read_text() == "nested"


def test_atomic_write_append(tmp_path):
    dest = tmp_path / "log.txt"
    dest.write_text("first\n")
    _atomic_write(dest, "second\n", append=True)
    assert dest.read_text() == "first\nsecond\n"


def test_archive_pre_write(tmp_path):
    os.chdir(tmp_path)
    dest = tmp_path / "target.txt"
    archive = _archive_pre_write(dest, "original payload")
    assert archive.exists()
    assert archive.read_text() == "original payload"
    assert ".warden-safe-cache" in str(archive)


def test_main_write_content(tmp_path, capsys):
    dest = tmp_path / "out.txt"
    rc = main([str(dest), "--content", "hello", "--IO-off", "--no-archive"])
    assert rc == 0
    assert dest.read_text() == "hello"
    output = json.loads(capsys.readouterr().out)
    assert output["dest"] == str(dest)


def test_main_dry_run(tmp_path, capsys):
    dest = tmp_path / "dry.txt"
    rc = main([str(dest), "--content", "payload", "--dry-run", "--IO-off"])
    assert rc == 0
    assert not dest.exists()
    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    assert "payload" in out


def test_main_diff_only(tmp_path, capsys):
    dest = tmp_path / "diff.txt"
    rc = main([str(dest), "--content", "text", "--diff-only", "--IO-off"])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["io_channel"] == "off"
    assert "audit_counts" in parsed


def test_main_check_only_clean(tmp_path, capsys):
    dest = tmp_path / "check.txt"
    rc = main([str(dest), "--content", "clean text", "--check-only", "--IO-off"])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "OK"


def test_main_append(tmp_path, capsys):
    dest = tmp_path / "append.txt"
    dest.write_text("existing\n")
    rc = main([str(dest), "--content", "new\n", "--append", "--IO-off", "--no-archive"])
    assert rc == 0
    assert dest.read_text() == "existing\nnew\n"


def test_main_conflicting_args(tmp_path):
    dest = tmp_path / "conflict.txt"
    with pytest.raises(SystemExit):
        main([str(dest), "--content", "x", "--append", "--dry-run"])


def test_main_check_only_conflicts(tmp_path):
    dest = tmp_path / "conflict2.txt"
    with pytest.raises(SystemExit):
        main([str(dest), "--content", "x", "--check-only", "--dry-run"])
