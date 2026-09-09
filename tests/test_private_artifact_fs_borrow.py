from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from harness.private_artifact_fs import PrivateArtifactError, open_artifact_root, root_identity, supported


def _assert_code(excinfo, code: str) -> None:
    assert excinfo.value.code == code


@pytest.mark.skipif(not supported(), reason="private artifact backend unsupported")
def test_retained_identity_and_borrow_shape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "payload.bin").write_bytes(b"value")
    expected = root_identity(root)
    with open_artifact_root(root, expected=expected, writable=False) as fs:
        assert fs.identity == expected
        with fs.borrow_descriptor() as borrowed:
            assert borrowed.identity == expected
            assert borrowed.platform == expected.platform
            assert (borrowed.fd is None) != (borrowed.handle is None)
        assert fs.read_bytes("payload.bin", max_bytes=5) == b"value"


@pytest.mark.skipif(not supported(), reason="private artifact backend unsupported")
def test_borrow_refuses_after_root_close(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    fs = open_artifact_root(root).__enter__()
    fs.close()
    with pytest.raises(PrivateArtifactError) as excinfo:
        fs.identity
    _assert_code(excinfo, "CLOSED")
    with pytest.raises(PrivateArtifactError) as excinfo:
        with fs.borrow_descriptor():
            pass
    _assert_code(excinfo, "CLOSED")


@pytest.mark.skipif(not supported(), reason="private artifact backend unsupported")
def test_borrow_reports_unsupported_when_duplicate_api_is_missing(monkeypatch, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    if os.name == "nt":
        import harness.private_artifact_fs_windows_tail as tail
        monkeypatch.delattr(tail._win, "duplicate_handle")
    else:
        import harness.private_artifact_fs_posix_tail as tail
        monkeypatch.delattr(tail.os, "dup")
    with open_artifact_root(root, writable=False) as fs:
        with pytest.raises(PrivateArtifactError) as excinfo:
            with fs.borrow_descriptor():
                pass
    _assert_code(excinfo, "UNSUPPORTED_OS")


@pytest.mark.skipif(os.name == "nt" or not supported(), reason="POSIX duplicate setup control")
def test_posix_set_inheritable_failure_closes_new_duplicate(monkeypatch, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "payload.bin").write_bytes(b"value")
    import errno
    import harness.private_artifact_fs_posix_tail as tail

    made: list[int] = []

    def fail_setup(fd: int, inheritable: bool) -> None:
        made.append(fd)
        raise OSError(errno.EIO, "synthetic close-on-exec failure")

    monkeypatch.setattr(tail.os, "set_inheritable", fail_setup)
    with open_artifact_root(root, writable=False) as fs:
        with pytest.raises(PrivateArtifactError) as excinfo:
            with fs.borrow_descriptor():
                pass
        assert fs.read_bytes("payload.bin", max_bytes=5) == b"value"
    _assert_code(excinfo, "IO_ERROR")
    assert made
    with pytest.raises(OSError):
        os.fstat(made[-1])


@pytest.mark.skipif(os.name == "nt" or not supported(), reason="POSIX borrow lifecycle control")
def test_posix_active_borrow_manager_reentry_refuses_before_second_dup(monkeypatch, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    import harness.private_artifact_fs_posix_tail as tail

    original = tail.duplicate_fd
    made: list[int] = []

    def record_dup(fd: int) -> int:
        dup = original(fd)
        made.append(dup)
        return dup

    monkeypatch.setattr(tail, "duplicate_fd", record_dup)
    with open_artifact_root(root, writable=False) as fs:
        manager = fs.borrow_descriptor()
        first = manager.__enter__()
        with pytest.raises(PrivateArtifactError) as excinfo:
            manager.__enter__()
        _assert_code(excinfo, "BUSY")
        assert made == [first.fd]
        manager.close()
        with pytest.raises(OSError):
            os.fstat(first.fd)
        with pytest.raises(PrivateArtifactError) as excinfo:
            manager.__enter__()
        _assert_code(excinfo, "CLOSED")
        assert made == [first.fd]


@pytest.mark.skipif(os.name == "nt" or not supported(), reason="POSIX borrowed fd control")
def test_posix_borrowed_fd_lifetime_and_no_path_reopen(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "payload.bin").write_bytes(b"original")
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    (replacement / "payload.bin").write_bytes(b"replacement")
    with open_artifact_root(root, writable=False) as fs:
        retained = fs.identity
        with fs.borrow_descriptor() as borrowed:
            fd = borrowed.fd
            assert fd is not None
            os.fstat(fd)
            old = tmp_path / "old-root"
            root.rename(old)
            replacement.rename(root)
            assert fs.identity == retained
            child = os.open("payload.bin", os.O_RDONLY, dir_fd=fd)
            try:
                assert os.read(child, 64) == b"original"
            finally:
                os.close(child)
        with pytest.raises(OSError):
            os.fstat(fd)
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(tmp_path / "old-root", ignore_errors=True)


@pytest.mark.skipif(os.name == "nt" or not supported(), reason="POSIX mismatch cleanup control")
def test_posix_borrow_mismatch_closes_wrong_duplicate(monkeypatch, tmp_path):
    root = tmp_path / "root"
    other = tmp_path / "other"
    root.mkdir(); other.mkdir()
    import harness.private_artifact_fs_posix_tail as tail

    other_fd = os.open(other, os.O_RDONLY | os.O_DIRECTORY)
    made: list[int] = []

    def wrong_dup(_fd: int) -> int:
        dup = os.dup(other_fd)
        made.append(dup)
        return dup

    monkeypatch.setattr(tail, "duplicate_fd", wrong_dup)
    try:
        with open_artifact_root(root, writable=False) as fs:
            with pytest.raises(PrivateArtifactError) as excinfo:
                with fs.borrow_descriptor():
                    pass
        _assert_code(excinfo, "UNSAFE_PATH")
        assert made
        with pytest.raises(OSError):
            os.fstat(made[-1])
    finally:
        os.close(other_fd)


@pytest.mark.skipif(os.name != "nt" or not supported(), reason="Windows borrowed handle control")
def test_windows_borrowed_handle_lifetime_independent(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    import harness.private_artifact_fs_windows as backend

    fs = open_artifact_root(root, writable=False).__enter__()
    try:
        with fs.borrow_descriptor() as borrowed:
            handle = borrowed.handle
            assert handle is not None
            assert borrowed.identity == fs.identity
            backend._win.handle_info(handle)
            fs.close()
            backend._win.handle_info(handle)
        with pytest.raises(OSError):
            backend._win.handle_info(handle)
        with pytest.raises(PrivateArtifactError) as excinfo:
            with fs.borrow_descriptor():
                pass
        _assert_code(excinfo, "CLOSED")
    finally:
        fs.close()


@pytest.mark.skipif(os.name != "nt" or not supported(), reason="Windows borrow lifecycle control")
def test_windows_active_borrow_manager_reentry_refuses_before_second_duplicate(monkeypatch, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    import harness.private_artifact_fs_windows as backend
    import harness.private_artifact_fs_windows_tail as tail

    original = tail.duplicate_handle
    made: list[int] = []

    def record_duplicate(handle: int) -> int:
        duplicate = original(handle)
        made.append(duplicate)
        return duplicate

    monkeypatch.setattr(tail, "duplicate_handle", record_duplicate)
    with open_artifact_root(root, writable=False) as fs:
        manager = fs.borrow_descriptor()
        first = manager.__enter__()
        with pytest.raises(PrivateArtifactError) as excinfo:
            manager.__enter__()
        _assert_code(excinfo, "BUSY")
        assert made == [first.handle]
        manager.close()
        with pytest.raises(OSError):
            backend._win.handle_info(first.handle)
        with pytest.raises(PrivateArtifactError) as excinfo:
            manager.__enter__()
        _assert_code(excinfo, "CLOSED")
        assert made == [first.handle]


@pytest.mark.skipif(os.name != "nt" or not supported(), reason="Windows mismatch cleanup control")
def test_windows_borrow_mismatch_closes_wrong_duplicate(monkeypatch, tmp_path):
    root = tmp_path / "root"
    other = tmp_path / "other"
    root.mkdir(); other.mkdir()
    import harness.private_artifact_fs_windows_tail as tail
    import harness.private_artifact_fs_windows as backend

    made: list[int] = []

    def wrong_duplicate(_handle: int) -> int:
        handle = backend._win.create_file(
            str(other),
            backend._win.GENERIC_READ | backend._win.SYNCHRONIZE,
            backend._win.FILE_SHARE_READ,
            backend._win.OPEN_EXISTING,
            backend._win.FILE_FLAG_BACKUP_SEMANTICS | backend._win.FILE_FLAG_OPEN_REPARSE_POINT,
        )
        made.append(handle)
        return handle

    monkeypatch.setattr(tail, "duplicate_handle", wrong_duplicate)
    with open_artifact_root(root, writable=False) as fs:
        with pytest.raises(PrivateArtifactError) as excinfo:
            with fs.borrow_descriptor():
                pass
    _assert_code(excinfo, "UNSAFE_PATH")
    assert made
    with pytest.raises(OSError):
        backend._win.handle_info(made[-1])
