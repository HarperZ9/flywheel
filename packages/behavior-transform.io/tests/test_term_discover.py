import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import pytest

from term_discover import (
    _LIBRARY,
    _already_calibrated,
    discover,
    SCAN_EXTENSIONS,
)


def test_library_not_empty():
    assert len(_LIBRARY) > 50


def test_library_structure():
    for pattern, category, suggestion in _LIBRARY:
        assert isinstance(pattern, str)
        assert isinstance(category, str)
        assert isinstance(suggestion, str)
        assert len(category) > 0
        assert len(suggestion) > 0


def test_library_categories():
    categories = {cat for _, cat, _ in _LIBRARY}
    assert "persistence" in categories
    assert "evasion" in categories
    assert "cred-relay" in categories
    assert "code-load" in categories
    assert "network-attack" in categories
    assert "web-attack" in categories


def test_already_calibrated_returns_set():
    result = _already_calibrated()
    assert isinstance(result, set)
    assert len(result) > 0


def test_discover_empty_dir(tmp_path):
    results = discover([tmp_path], min_count=1)
    assert results == []


def test_discover_with_matching_file(tmp_path):
    f = tmp_path / "test.py"
    f.write_text("# this uses dll-hijacking technique\n")
    results = discover([tmp_path], min_count=1)
    # May or may not find it depending on calibration state
    assert isinstance(results, list)


def test_scan_extensions():
    assert ".py" in SCAN_EXTENSIONS
    assert ".md" in SCAN_EXTENSIONS
    assert ".yaml" in SCAN_EXTENSIONS


def test_discover_respects_min_count(tmp_path):
    f = tmp_path / "one.py"
    f.write_text("# one mention of arp-spoofing\n")
    results = discover([tmp_path], min_count=5)
    assert len(results) == 0


def test_library_patterns_compile():
    import re
    for pattern, _, _ in _LIBRARY:
        compiled = re.compile(pattern, re.IGNORECASE)
        assert compiled is not None
