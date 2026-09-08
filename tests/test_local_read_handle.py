"""Descriptor binding controls for local read_file."""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

from harness.local_tools import ToolExecutor


def test_public_read_file_rejects_swap_sandwich_opened_handle_outside_root(
        tmp_path, monkeypatch):
    from harness import local_read_file

    root = tmp_path / "root"
    root.mkdir()
    victim = root / "victim.txt"
    victim.write_text("INSIDE", encoding="utf-8")
    outside = tmp_path / "outside-private-token.txt"
    outside.write_text("OUTSIDE", encoding="utf-8")
    real_open = local_read_file.os.open
    real_stat = local_read_file.os.stat

    def sandwich_open(target, flags, *args, **kwargs):
        if os.path.realpath(os.fspath(target)) == os.path.realpath(str(victim)):
            return real_open(str(outside), flags, *args, **kwargs)
        return real_open(target, flags, *args, **kwargs)

    def sandwich_stat(target, *args, **kwargs):
        if os.path.realpath(os.fspath(target)) == os.path.realpath(str(victim)):
            return real_stat(str(outside), *args, **kwargs)
        return real_stat(target, *args, **kwargs)

    monkeypatch.setattr(local_read_file.os, "open", sandwich_open)
    monkeypatch.setattr(local_read_file.os, "stat", sandwich_stat)

    result = ToolExecutor(root=str(root), max_output=512).execute(
        "read_file", {"path": "victim.txt", "offset": 0})

    assert not result.ok
    assert result.output == "[error] read_file_path_escaped (escapes root)"
    assert "OUTSIDE" not in result.output


def test_read_file_fails_closed_when_handle_path_is_unsupported(tmp_path, monkeypatch):
    from harness import local_read_handle

    (tmp_path / "x").write_text("abc", encoding="utf-8")
    monkeypatch.setattr(local_read_handle, "_opened_handle_path", lambda fd: None)

    result = ToolExecutor(root=str(tmp_path)).execute("read_file", {"path": "x"})

    assert not result.ok
    assert result.output == "[error] read_file_handle_path_unsupported"


def test_windows_handle_namespace_normalization_is_bounded():
    from harness.local_read_handle import _strip_windows_namespace

    assert _strip_windows_namespace(
        "\\\\?\\C:\\root\\file.txt") == "C:\\root\\file.txt"
    assert _strip_windows_namespace(
        "\\\\?\\UNC\\server\\share\\root\\file.txt"
    ) == "\\\\server\\share\\root\\file.txt"
    assert _strip_windows_namespace(
        "\\\\?\\Volume{00000000-0000-0000-0000-000000000000}\\root"
    ) == "\\\\?\\Volume{00000000-0000-0000-0000-000000000000}\\root"


def test_windows_handle_path_compares_inside_current_volume(tmp_path):
    if os.name != "nt":
        pytest.skip("Windows handle path API only")
    from harness.local_read_handle import (
        _canonical_compare_path, _windows_handle_path, open_confined_read_handle)

    path = tmp_path / "x.txt"
    path.write_text("abc", encoding="utf-8")
    opened = open_confined_read_handle(str(tmp_path), str(path))
    assert not isinstance(opened, str), opened
    try:
        root_cmp = _canonical_compare_path(str(tmp_path))
        handle_cmp = _canonical_compare_path(_windows_handle_path(opened.fd))
        assert root_cmp is not None
        assert handle_cmp is not None
        assert os.path.commonpath([root_cmp, handle_cmp]) == root_cmp
    finally:
        os.close(opened.fd)


def test_darwin_handle_path_uses_f_getpath(monkeypatch):
    from harness import local_read_handle

    calls = []

    def fake_fcntl(fd, cmd, buf):
        calls.append((fd, cmd, len(buf)))
        return b"/tmp/root/file.txt\0" + b"x" * 8

    monkeypatch.setattr(local_read_handle.sys, "platform", "darwin")
    monkeypatch.setattr(local_read_handle, "os", SimpleNamespace(name="posix"))
    monkeypatch.setitem(sys.modules, "fcntl", SimpleNamespace(fcntl=fake_fcntl))

    assert local_read_handle._opened_handle_path(7) == "/tmp/root/file.txt"
    assert calls == [(7, 50, 1024)]


@pytest.mark.parametrize("result", [b"", b"relative\0", b"/unterminated", 0])
def test_darwin_handle_path_rejects_invalid_api_result(monkeypatch, result):
    from harness.local_read_handle import _darwin_handle_path

    monkeypatch.setitem(sys.modules, "fcntl", SimpleNamespace(
        fcntl=lambda fd, cmd, buf: result))

    assert _darwin_handle_path(7) is None


def test_darwin_handle_path_api_failure_is_closed(monkeypatch):
    from harness.local_read_handle import _darwin_handle_path

    def failed_fcntl(fd, cmd, buf):
        raise OSError("private host details")

    monkeypatch.setitem(sys.modules, "fcntl", SimpleNamespace(fcntl=failed_fcntl))

    assert _darwin_handle_path(7) is None


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin F_GETPATH API only")
def test_darwin_handle_path_reads_real_descriptor(tmp_path):
    from harness.local_read_handle import _darwin_handle_path

    path = tmp_path / "x"
    path.write_bytes(b"abc")
    with path.open("rb") as source:
        resolved = _darwin_handle_path(source.fileno())
        assert resolved is not None
        assert os.path.samefile(resolved, path)
