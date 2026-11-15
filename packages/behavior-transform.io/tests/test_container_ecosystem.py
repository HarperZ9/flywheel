import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import json
import pytest
from unittest.mock import patch, MagicMock

from container_ecosystem import (
    CHANNELS,
    EXPECTED_HOOKS,
    _channel_sym,
    _toggle_is_armed,
    _toggle_read_config,
    main,
)


def test_channels_structure():
    assert len(CHANNELS) == 10
    for ch in CHANNELS:
        assert "name" in ch
        assert "desc" in ch
        assert "handler" in ch
        assert "mode" in ch


def test_channel_names_unique():
    names = [ch["name"] for ch in CHANNELS]
    assert len(names) == len(set(names))


def test_expected_hooks_structure():
    assert len(EXPECTED_HOOKS) >= 8
    for event, hook in EXPECTED_HOOKS:
        assert isinstance(event, str)
        assert hook.endswith(".py")


def test_channel_sym_enforced():
    ch = {"name": "TEST", "handler": "safe_read.py", "mode": "enforced"}
    sym, label = _channel_sym(ch)
    assert sym == "+"
    assert "Enforced" in label


def test_channel_sym_partial():
    ch = {"name": "TEST", "handler": "safe_exec.py", "mode": "partial"}
    sym, label = _channel_sym(ch)
    assert sym == "~"
    assert "Partial" in label


def test_channel_sym_server():
    ch = {"name": "TEST", "handler": "mcp_calibrate.py", "mode": "server"}
    sym, label = _channel_sym(ch)
    assert sym == "o"
    assert "Svr" in label


def test_channel_sym_proxy():
    ch = {"name": "TEST", "handler": "warden_mcp_proxy.py", "mode": "proxy"}
    sym, label = _channel_sym(ch)
    assert sym in ("+", "!")


def test_toggle_read_config_missing(tmp_path):
    with patch("container_ecosystem._CLEANROOM_CONFIG", tmp_path / "nonexistent.json"):
        cfg = _toggle_read_config()
    assert cfg == {}


def test_toggle_read_config_valid(tmp_path):
    cfg_file = tmp_path / "cleanroom.json"
    cfg_file.write_text(json.dumps({"active": True}))
    with patch("container_ecosystem._CLEANROOM_CONFIG", cfg_file):
        cfg = _toggle_read_config()
    assert cfg["active"] is True


def test_main_no_args(capsys):
    rc = main([])
    assert rc == 0


def test_main_unknown_subcommand(capsys):
    rc = main(["unknown_xyz"])
    assert rc == 2


def test_main_status(capsys):
    rc = main(["status"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Channel" in out or "Container" in out


def test_channel_modes_valid():
    valid_modes = {"enforced", "partial", "server", "proxy"}
    for ch in CHANNELS:
        assert ch["mode"] in valid_modes
