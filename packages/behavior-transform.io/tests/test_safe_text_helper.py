import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import json
import pytest
from unittest.mock import patch
from io import StringIO

from safe_text_helper import main


def test_main_json_mode():
    with patch("sys.stdin", StringIO("clean text")):
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            rc = main(["--json"])
    assert rc == 0
    parsed = json.loads(mock_out.getvalue())
    assert parsed["status"] == "ok"
    assert "audit_counts" in parsed
    assert "total" in parsed


def test_main_diff_only():
    with patch("sys.stdin", StringIO("clean text")):
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            rc = main(["--diff-only"])
    assert rc == 0
    parsed = json.loads(mock_out.getvalue())
    assert parsed["status"] == "ok"


def test_main_passthrough():
    with patch("sys.stdin", StringIO("hello world")):
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            rc = main([])
    assert rc == 0
    assert "hello world" in mock_out.getvalue()


def test_main_empty_input():
    with patch("sys.stdin", StringIO("")):
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            rc = main([])
    assert rc == 0


def test_main_changed_field():
    with patch("sys.stdin", StringIO("some text")):
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            rc = main(["--json"])
    assert rc == 0
    parsed = json.loads(mock_out.getvalue())
    assert "changed" in parsed
    assert isinstance(parsed["changed"], bool)
