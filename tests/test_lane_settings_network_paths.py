"""The granted lane settings refuse network paths, and the Node pin holds within a process.

Security review of the 1.1.0 change, finding 7:

- ``settings.node_path`` and ``lane.root`` refuse a UNC, device or mapped
  network path before any filesystem call. Resolving or probing such a path
  opens an SMB session (which can carry the user's NTLM response), and the
  server behind it controls the bytes, the size and the time stamp of the
  file, so no pin taken from it can hold at launch.
- The saved Node choice is hashed again at every launch. A replacement that
  keeps the size and the modification time is refused as well.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from harness import path_identity
from harness.lane_settings_route import node_path_post, root_post

SHARES = [r"\\srv\share\node.exe", "//srv/share/node.exe", r"\\?\UNC\srv\share\node.exe",
          r"\\?\C:\tools\node.exe", r"\??\C:\tools\node.exe"]


def _networkish(value) -> bool:
    text = os.fspath(value).replace("/", "BS").replace(chr(92), "BS")
    return text.startswith("BSBS") or "srv" in text or text.startswith("BS??")


@pytest.fixture
def no_filesystem(monkeypatch):
    """A filesystem call on any of the network spellings fails the test."""
    def guard(original):
        def call(target, *args, **kwargs):
            if _networkish(target):
                raise AssertionError(f"a filesystem call was made on {target!r}")
            return original(target, *args, **kwargs)
        return call
    for name in ("resolve", "is_file", "is_dir", "exists", "stat", "open"):
        monkeypatch.setattr(Path, name, guard(getattr(Path, name)))
    monkeypatch.setattr(os, "stat", guard(os.stat))
    monkeypatch.setattr(os.path, "isdir", guard(os.path.isdir))


@pytest.mark.parametrize("raw", SHARES)
def test_a_network_node_path_is_refused_before_any_filesystem_call(raw, no_filesystem):
    body, status = node_path_post({"path": raw}, {"FLYWHEEL_HOME": "unused"},
                                  version_probe=lambda _p: "v22.0.0", platform="nt")
    assert (status, body["reason"]) == (400, "path_on_network")


@pytest.mark.parametrize("raw", [r"\\srv\share\project", "//srv/share/project",
                                 r"\\?\C:\project"])
def test_a_network_project_folder_is_refused_before_any_filesystem_call(
        raw, monkeypatch, no_filesystem):
    monkeypatch.setattr(path_identity, "_WINDOWS", True)
    body, status = root_post({"path": raw}, {"FLYWHEEL_HOME": "unused"})
    assert (status, body["reason"]) == (400, "path_on_network")


def test_a_mapped_network_drive_is_refused(tmp_path, monkeypatch):
    node = tmp_path / "node.exe"
    node.write_bytes(b"node")
    monkeypatch.setattr(path_identity, "remote_drive", lambda _text, **_k: True)
    body, status = node_path_post({"path": str(node)}, {"FLYWHEEL_HOME": str(tmp_path)},
                                  version_probe=lambda _p: "v22.0.0", platform="nt")
    assert (status, body["reason"]) == (400, "path_on_network")
    assert not (tmp_path / "node_path").exists()


def test_remote_drive_reads_the_drive_type_of_the_drive_root_only():
    seen = []
    kinds = {"Z:\\": 4, "C:\\": 3}

    def drive_type(root):
        seen.append(root)
        return kinds[root]
    assert path_identity.remote_drive("Z:\\tools\\node.exe", windows=True,
                                      drive_type=drive_type) is True
    assert path_identity.remote_drive("c:/tools/node.exe", windows=True,
                                      drive_type=drive_type) is False
    assert path_identity.remote_drive("relative\\node.exe", windows=True,
                                      drive_type=drive_type) is False
    assert path_identity.remote_drive("Z:\\x", windows=False, drive_type=drive_type) is False
    assert seen == ["Z:\\", "C:\\"]


def test_a_replacement_that_keeps_size_and_mtime_is_not_run(tmp_path):
    from harness.tool_discovery import find_node
    home = tmp_path / "home"
    node = tmp_path / "tools" / "node.exe"
    node.parent.mkdir()
    node.write_bytes(b"original")
    env = {"FLYWHEEL_HOME": str(home)}
    _body, status = node_path_post({"path": str(node)}, env,
                                   version_probe=lambda _p: "v22.0.0", platform="nt")
    assert status == 200
    probe = lambda _path: "v22.0.0"  # noqa: E731
    first = find_node(env, home=home, node_version=probe, platform="nt",
                      read_registry_path=lambda _s: None)
    assert first.found and first.source == "node_path"
    stat = node.stat()
    node.write_bytes(b"replaced")                      # same length as "original"
    os.utime(node, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert node.stat().st_size == stat.st_size and node.stat().st_mtime_ns == stat.st_mtime_ns
    again = find_node(env, home=home, node_version=probe, platform="nt",
                      read_registry_path=lambda _s: None)
    assert not again.found and "changed since it was chosen" in again.detail
