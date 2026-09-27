"""The per-user home pointer: tests never write it, a second gateway does not
take it from a live one, and a hook never follows it to a network path.

Correctness review F4 and F10, security review 1 and 3 of 1.1.0:

- the suite rewrote the developer's real pointer (a pytest temp home was
  found in it after an integration run), because three tests reach
  ``publish_endpoint`` through ``gateway.main``;
- any second gateway with another home took the pointer from the owner's
  running gateway, last writer wins, and nothing said so;
- the pointer location follows ``USERPROFILE`` on Windows, so a settings
  ``env`` block can choose which pointer a hook reads, and a pointer naming
  ``\\\\host\\share`` made the hook open an SMB session.
"""
from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import pytest

from harness import gateway_endpoint_file as endpoint_file
from harness.capture_hooks import home as home_module


def test_the_suite_points_the_home_pointer_at_a_temp_file(tmp_path_factory):
    base = Path(tmp_path_factory.getbasetemp()).resolve()
    for found in (home_module.pointer_path(), endpoint_file.pointer_path()):
        assert found is not None
        assert Path(found).resolve().is_relative_to(base), found


class _Server:
    def __init__(self, port):
        self.server_address = ("127.0.0.1", port)


def _live_home(tmp_path, name):
    """A home whose gateway.endpoint names this process and a listener it holds."""
    home = tmp_path / name
    home.mkdir()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    endpoint_file.write_endpoint(home, "127.0.0.1", listener.getsockname()[1], os.getpid())
    return home, listener


def _pointer_home(target: Path) -> str:
    return json.loads(target.read_bytes())["home"]


def test_a_second_gateway_does_not_take_a_live_gateway_s_pointer(tmp_path, monkeypatch):
    target = tmp_path / "pointer" / "home.json"
    monkeypatch.setattr(endpoint_file, "pointer_path", lambda: target)
    owner, listener = _live_home(tmp_path, "owner-home")
    try:
        endpoint_file.write_pointer(owner, target)
        other = tmp_path / "second-home"
        other.mkdir()
        monkeypatch.setattr(endpoint_file.os, "getpid", lambda: 1)   # a different gateway
        endpoint_file.publish_endpoint(other, [_Server(1)])
        assert _pointer_home(target) == str(owner)
    finally:
        listener.close()


def test_a_pointer_whose_gateway_is_gone_is_taken(tmp_path, monkeypatch):
    target = tmp_path / "pointer" / "home.json"
    monkeypatch.setattr(endpoint_file, "pointer_path", lambda: target)
    stale = tmp_path / "stale-home"
    stale.mkdir()
    endpoint_file.write_endpoint(stale, "127.0.0.1", 9, 2 ** 22 + 7)   # no such process
    endpoint_file.write_pointer(stale, target)
    fresh = tmp_path / "fresh-home"
    fresh.mkdir()
    endpoint_file.publish_endpoint(fresh, [_Server(1)])
    assert _pointer_home(target) == str(fresh)


@pytest.mark.parametrize("spelling", ["\\\\host.invalid\\share\\home",
                                      "//host.invalid/share/home", "\\\\?\\C:\\home"])
def test_a_hook_refuses_a_network_or_device_home_before_any_filesystem_call(
        spelling, tmp_path, monkeypatch):
    monkeypatch.setattr(home_module, "_WINDOWS", True)

    def refuse(*_a, **_k):
        raise AssertionError("a filesystem call was made on the home")
    monkeypatch.setattr(home_module, "in_git_worktree", refuse)
    pointer = tmp_path / "home.json"
    pointer.write_text(json.dumps({"schema": home_module.POINTER_SCHEMA, "home": spelling}),
                       encoding="utf-8")
    monkeypatch.setattr(home_module.os.path, "isabs", lambda _p: True)
    _home, code = home_module.resolve_home(None, {}, tmp_path, pointer=pointer)
    assert code == "HOME_NOT_LOCAL"
    _home, code = home_module.resolve_home(spelling, {}, tmp_path)
    assert code == "HOME_NOT_LOCAL"


def test_the_doctor_names_a_pointer_that_leads_elsewhere(tmp_path, monkeypatch):
    from harness import trace_doctor_checks as checks
    target = tmp_path / "pointer" / "home.json"
    monkeypatch.setattr(home_module, "pointer_path", lambda: target)
    mine, other = tmp_path / "mine", tmp_path / "other"
    mine.mkdir()
    other.mkdir()
    endpoint_file.write_pointer(other, target)
    state, detail, remedy = checks.location_check(mine, {})
    assert state == "WARN" and "pointer" in detail and "--home" in remedy
    endpoint_file.write_pointer(mine, target)
    assert checks.location_check(mine, {})[0] == "PASS"
