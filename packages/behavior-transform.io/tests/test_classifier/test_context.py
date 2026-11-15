import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

import pytest
from classifier import _context


def test_split_paragraphs_empty():
    result = _context._split_paragraphs("")
    assert isinstance(result, list)


def test_split_paragraphs_single():
    result = _context._split_paragraphs("hello world")
    assert len(result) >= 1
    assert any("hello world" in seg for _, seg in result)


def test_split_paragraphs_multi():
    result = _context._split_paragraphs("para one\n\npara two")
    assert len(result) == 2


def test_context_files_returns_list():
    result = _context._context_files()
    assert isinstance(result, list)


def test_validate_file_returns_dict(tmp_path):
    f = tmp_path / "test.py"
    f.write_text("x = 1")
    result = _context.validate_file(f, include_tier2=False)
    assert isinstance(result, dict)


def test_annotate_file_returns_list(tmp_path):
    f = tmp_path / "test.py"
    f.write_text("x = 1")
    result = _context.annotate_file(f, include_tier2=False)
    assert isinstance(result, list)


def test_analyze_context_returns_list():
    result = _context.analyze_context(include_tier2=False)
    assert isinstance(result, list)


def test_ctx_fix_returns_list():
    result = _context.ctx_fix(include_tier2=False, dry_run=True)
    assert isinstance(result, list)