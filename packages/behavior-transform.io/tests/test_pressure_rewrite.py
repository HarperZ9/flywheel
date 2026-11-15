import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import pytest

from pressure_rewrite import (
    _preserve_case,
    _is_whitelisted,
    _process_text,
    SCAN_EXTENSIONS,
    SKIP_DIRS,
    PROSE_SCOPES,
)


def test_preserve_case_upper():
    assert _preserve_case("HELLO", "world") == "WORLD"


def test_preserve_case_title():
    assert _preserve_case("Hello", "world") == "World"


def test_preserve_case_lower():
    assert _preserve_case("hello", "World") == "World"


def test_scan_extensions():
    assert ".py" in SCAN_EXTENSIONS
    assert ".md" in SCAN_EXTENSIONS
    assert ".yaml" in SCAN_EXTENSIONS
    assert ".toml" in SCAN_EXTENSIONS


def test_skip_dirs():
    assert ".git" in SKIP_DIRS
    assert "__pycache__" in SKIP_DIRS
    assert "node_modules" in SKIP_DIRS
    assert "venv" in SKIP_DIRS


def test_prose_scopes():
    assert "free-prose" in PROSE_SCOPES
    assert "verb-prose" in PROSE_SCOPES
    assert "noun-prose" in PROSE_SCOPES


def test_process_text_no_matches():
    text, n = _process_text("clean text", [])
    assert text == "clean text"
    assert n == 0


def test_is_whitelisted_false(tmp_path):
    p = tmp_path / "regular" / "file.py"
    assert not _is_whitelisted(p)
