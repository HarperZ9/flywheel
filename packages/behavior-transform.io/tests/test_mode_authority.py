from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOOKS = REPO / "hooks"
TOOLS = REPO / "tools"

sys.path.insert(0, str(HOOKS))
sys.path.insert(0, str(TOOLS))


def test_cleanroom_active_derives_from_io_state_on(monkeypatch):
    """cleanroom_active returns (True, True) when io_state says 'on'."""
    monkeypatch.setenv("WARDEN_IO_CHANNEL", "on")
    monkeypatch.setenv("BEHAVIOR_TRANSFORM_TOOLS", str(TOOLS))
    import importlib
    import _warden_cleanroom
    importlib.reload(_warden_cleanroom)
    armed, tag = _warden_cleanroom.cleanroom_active("test-hook")
    assert armed is True
    assert tag is True


def test_cleanroom_active_derives_from_io_state_off(monkeypatch):
    """cleanroom_active returns (False, False) when io_state says 'off'."""
    monkeypatch.setenv("WARDEN_IO_CHANNEL", "off")
    monkeypatch.setenv("BEHAVIOR_TRANSFORM_TOOLS", str(TOOLS))
    import importlib
    import _warden_cleanroom
    importlib.reload(_warden_cleanroom)
    armed, tag = _warden_cleanroom.cleanroom_active("test-hook")
    assert armed is False
    assert tag is False
