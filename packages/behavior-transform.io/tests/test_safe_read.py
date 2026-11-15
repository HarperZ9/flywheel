import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import json
import os
import pytest

from safe_read import _read_source, _summary, _parse_lines, _cache_path, main


def test_read_source_full(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("line1\nline2\nline3\n")
    text = _read_source(f, None)
    assert text == "line1\nline2\nline3\n"


def test_read_source_lines(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("a\nb\nc\nd\ne\n")
    text = _read_source(f, (2, 4))
    assert "b" in text
    assert "d" in text
    assert "e" not in text


def test_summary(tmp_path):
    f = tmp_path / "test.py"
    content = "import os\n\ndef foo():\n    pass\n\nclass Bar:\n    pass\n"
    f.write_text(content)
    s = _summary(content, f)
    assert s["line_count"] == 7
    assert s["structure"]["def_count"] == 1
    assert s["structure"]["class_count"] == 1
    assert s["structure"]["import_count"] == 1
    assert "sha256_prefix" in s


def test_parse_lines_valid():
    assert _parse_lines("10:20") == (10, 20)


def test_parse_lines_invalid():
    import argparse
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_lines("nocolon")


def test_cache_path(tmp_path):
    src = tmp_path / "some" / "file.py"
    result = _cache_path(src)
    assert ".warden-safe-cache" in str(result)
    assert result.suffix == ".safe"


def test_main_full_read(tmp_path, capsys):
    f = tmp_path / "hello.txt"
    f.write_text("hello world\n")
    rc = main([str(f), "--IO-off"])
    assert rc == 0
    assert "hello world" in capsys.readouterr().out


def test_main_hash_mode(tmp_path, capsys):
    f = tmp_path / "data.txt"
    f.write_text("some content\n")
    rc = main([str(f), "--hash"])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert "hash_only" in parsed
    assert "sha256_prefix" in parsed["hash_only"]


def test_main_summary_mode(tmp_path, capsys):
    f = tmp_path / "code.py"
    f.write_text("def hello():\n    pass\n")
    rc = main([str(f), "--summary", "--IO-off"])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["structure"]["def_count"] == 1


def test_main_diff_only(tmp_path, capsys):
    f = tmp_path / "test.txt"
    f.write_text("clean text\n")
    rc = main([str(f), "--diff-only", "--IO-off"])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["audit_counts"] == {"tier1": 0, "tier2": 0}


def test_main_lines_range(tmp_path, capsys):
    f = tmp_path / "multi.txt"
    f.write_text("a\nb\nc\nd\ne\n")
    rc = main([str(f), "--lines", "2:3", "--IO-off"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "b" in out
    assert "c" in out


def test_main_file_not_found(capsys):
    rc = main(["/nonexistent/path/file.txt"])
    assert rc == 2


def test_main_to_cache(tmp_path, capsys):
    f = tmp_path / "cached.txt"
    f.write_text("cache me\n")
    os.chdir(tmp_path)
    rc = main([str(f), "--to-cache", "--IO-off"])
    assert rc == 0
    cache_dir = tmp_path / ".warden-safe-cache"
    assert cache_dir.exists()
