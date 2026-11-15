import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import pytest

from io_mode import (
    _action_mode,
    _action_profile,
    default_bin_dir,
    _status_payload,
)


def test_action_mode_on_actions():
    for action in ("on", "standard", "ops", "security", "defense", "offense", "opsec"):
        assert _action_mode(action) == "on", f"expected 'on' for {action}"


def test_action_mode_off_actions():
    for action in ("off", "research", "academic"):
        assert _action_mode(action) == "off", f"expected 'off' for {action}"


def test_action_mode_invalid():
    with pytest.raises(ValueError):
        _action_mode("garbage")


def test_action_profile_ops():
    assert _action_profile("ops") == "ops"
    assert _action_profile("security") == "ops"


def test_action_profile_research():
    assert _action_profile("research") == "research"


def test_action_profile_academic():
    assert _action_profile("academic") == "academic"


def test_default_bin_dir_returns_path():
    result = default_bin_dir()
    assert isinstance(result, Path)
    assert "bin" in str(result)


def test_status_payload_keys():
    payload = _status_payload()
    assert "mode" in payload
    assert "profile" in payload
    assert "hook_layer" in payload
    assert "state_file" in payload
