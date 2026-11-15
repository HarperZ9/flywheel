import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import json
import pytest
from unittest.mock import patch

from session_start import _context, _precommit_status, main, TOOLS_ROOT, REPO_ROOT


def test_tools_root_exists():
    assert TOOLS_ROOT.is_dir()


def test_repo_root_exists():
    assert REPO_ROOT.is_dir()


def test_precommit_status():
    status = _precommit_status()
    assert status in ("installed", "missing")


def test_context_returns_string():
    ctx = _context("test-surface")
    assert isinstance(ctx, str)
    assert "test-surface" in ctx
    assert "behavior-transform" in ctx


def test_context_includes_mode():
    ctx = _context("codex")
    assert "IO mode" in ctx


def test_main_default(capsys):
    rc = main([])
    assert rc == 0
    output = capsys.readouterr().out
    parsed = json.loads(output)
    assert "additionalContext" in parsed
    assert "behavior-transform" in parsed["additionalContext"]


def test_main_custom_surface(capsys):
    rc = main(["--surface", "claude-code"])
    assert rc == 0
    output = capsys.readouterr().out
    parsed = json.loads(output)
    assert "claude-code" in parsed["additionalContext"]


def test_main_always_succeeds(capsys):
    with patch("session_start._load_io_state", return_value=None):
        rc = main(["--surface", "broken"])
    assert rc == 0
    output = capsys.readouterr().out
    parsed = json.loads(output)
    assert "additionalContext" in parsed
