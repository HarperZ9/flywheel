from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from harness.private_artifact_fs import PrivateArtifactError, open_artifact_root, root_identity, supported


def _assert_code(excinfo, code: str) -> None:
    assert excinfo.value.code == code


def _close_windows_handle_if_open(backend, handle: int | None) -> bool:
    if handle is None:
        return True
    try:
        backend._win.handle_info(handle)
    except OSError:
        return True
    backend._win.close_handle(handle)
    return False


@pytest.mark.skipif(os.name != "nt" or not supported(), reason="Windows handle acquisition control")
def test_windows_root_identity_failure_closes_acquired_root_handle(monkeypatch, tmp_path):
    root = tmp_path / "root-acquire-target"
    root.mkdir()
    import harness.private_artifact_fs_windows as backend

    original_create = backend._win.nt_create_relative
    original_identity = backend._handle_identity
    state: dict[str, int | str] = {}

    def create(parent, name, access, share, disposition, options):
        handle = original_create(parent, name, access, share, disposition, options)
        state["name"] = name; state["handle"] = handle
        return handle

    def fail_for_root(handle):
        if state.get("name") == root.name:
            raise OSError(errno.EIO, "synthetic identity failure")
        return original_identity(handle)

    monkeypatch.setattr(backend._win, "nt_create_relative", create)
    monkeypatch.setattr(backend, "_handle_identity", fail_for_root)
    try:
        with pytest.raises(PrivateArtifactError) as excinfo:
            root_identity(root)
        _assert_code(excinfo, "IO_ERROR")
        assert _close_windows_handle_if_open(backend, state.get("handle"))
    finally:
        monkeypatch.setattr(backend._win, "nt_create_relative", original_create)
        monkeypatch.setattr(backend, "_handle_identity", original_identity)


@pytest.mark.skipif(os.name != "nt" or not supported(), reason="Windows descendant acquisition control")
def test_windows_descendant_identity_failure_closes_acquired_child_handle(monkeypatch, tmp_path):
    root = tmp_path / "root"
    (root / "aa").mkdir(parents=True)
    import harness.private_artifact_fs_windows as backend

    original_create = backend._win.nt_create_relative
    original_identity = backend._handle_identity
    state: dict[str, int | str] = {}

    def create(parent, name, access, share, disposition, options):
        handle = original_create(parent, name, access, share, disposition, options)
        state["name"] = name; state["handle"] = handle
        return handle

    def fail_for_child(handle):
        if state.get("name") == "aa":
            raise OSError(errno.EIO, "synthetic child identity failure")
        return original_identity(handle)

    with open_artifact_root(root) as fs:
        monkeypatch.setattr(backend._win, "nt_create_relative", create)
        monkeypatch.setattr(backend, "_handle_identity", fail_for_child)
        try:
            with pytest.raises(PrivateArtifactError) as excinfo:
                fs.read_bytes("aa/missing.bin", max_bytes=1)
            _assert_code(excinfo, "IO_ERROR")
            assert _close_windows_handle_if_open(backend, state.get("handle"))
        finally:
            monkeypatch.setattr(backend._win, "nt_create_relative", original_create)
            monkeypatch.setattr(backend, "_handle_identity", original_identity)


@pytest.mark.skipif(os.name == "nt" or not supported(), reason="POSIX fd acquisition control")
def test_posix_root_identity_failure_closes_acquired_root_fd(monkeypatch, tmp_path):
    root = tmp_path / "root-acquire-target"
    root.mkdir()
    import harness.private_artifact_fs as facade
    import harness.private_artifact_fs_posix as backend

    original_open = backend.os.open
    original_fstat = backend.os.fstat
    state: dict[str, int | str] = {}

    def open_record(name, flags, mode=0o777, *, dir_fd=None):
        fd = original_open(name, flags, mode, dir_fd=dir_fd)
        if name == root.name:
            state["fd"] = fd
        return fd

    def fstat_fail(fd):
        if fd == state.get("fd"):
            raise OSError(errno.EIO, "synthetic identity failure")
        return original_fstat(fd)

    monkeypatch.setattr(backend.os, "open", open_record)
    monkeypatch.setattr(backend.os, "fstat", fstat_fail)
    monkeypatch.setattr(backend, "supported", lambda: True)
    monkeypatch.setattr(facade, "_backend", lambda: backend)
    with pytest.raises(PrivateArtifactError) as excinfo:
        root_identity(root)
    _assert_code(excinfo, "IO_ERROR")
    leaked = state.get("fd")
    assert leaked is not None
    with pytest.raises(OSError):
        original_fstat(leaked)


@pytest.mark.skipif(os.name == "nt" or not supported(), reason="POSIX descendant acquisition control")
def test_posix_descendant_identity_failure_closes_acquired_child_fd(monkeypatch, tmp_path):
    root = tmp_path / "root"
    (root / "aa").mkdir(parents=True)
    import harness.private_artifact_fs_posix as backend

    original_open = backend.os.open
    original_fstat = backend.os.fstat
    state: dict[str, int | str] = {}

    def open_record(name, flags, mode=0o777, *, dir_fd=None):
        fd = original_open(name, flags, mode, dir_fd=dir_fd)
        if name == "aa":
            state["fd"] = fd
        return fd

    def fstat_fail(fd):
        if fd == state.get("fd"):
            raise OSError(errno.EIO, "synthetic child identity failure")
        return original_fstat(fd)

    with open_artifact_root(root) as fs:
        monkeypatch.setattr(backend.os, "open", open_record)
        monkeypatch.setattr(backend.os, "fstat", fstat_fail)
        with pytest.raises(PrivateArtifactError) as excinfo:
            fs.read_bytes("aa/missing.bin", max_bytes=1)
    _assert_code(excinfo, "IO_ERROR")
    leaked = state.get("fd")
    assert leaked is not None
    with pytest.raises(OSError):
        original_fstat(leaked)


@pytest.mark.skipif(os.name == "nt" or not supported(), reason="POSIX fsync errno control")
def test_posix_bad_directory_fsync_fails_public_publication(monkeypatch, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    import harness.private_artifact_fs_posix as backend
    import harness.private_artifact_fs_posix_tail as tail

    monkeypatch.setattr(backend, "_fsync_dir", lambda _fd: tail.fsync_dir(1_000_000))
    with open_artifact_root(root) as fs:
        with pytest.raises(PrivateArtifactError) as excinfo:
            fs.write_new_or_same("payload.bin", b"exact")
    _assert_code(excinfo, "IO_ERROR")
    if (root / "payload.bin").exists():
        assert (root / "payload.bin").read_bytes() == b"exact"


def test_public_plan_qualifies_windows_permission_claim():
    doc = Path(__file__).resolve().parents[1] / "docs" / "superpowers" / "plans" / "2026-09-08-private-artifact-fs.md"
    text = doc.read_text(encoding="utf-8")
    assert "Windows inherits the admitted root permissions" in text
    assert "admitted root ACL" in text
