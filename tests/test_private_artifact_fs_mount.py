from __future__ import annotations

import os
import stat

import pytest

from harness.private_artifact_fs import PrivateArtifactError, open_artifact_root


pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX mount admission controls")


def _fd_for(path) -> int:
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0))


def _device_pair(fd: int) -> str:
    st = os.fstat(fd)
    return f"{os.major(st.st_dev)}:{os.minor(st.st_dev)}"


def test_mount_admission_refuses_unknown_fd_device(monkeypatch, tmp_path):
    import harness.private_artifact_fs_mount as mount

    if not mount.supported():
        pytest.skip("mountinfo admission unavailable")
    fd = _fd_for(tmp_path)
    try:
        monkeypatch.setattr(mount, "_mountinfo_lines", lambda: ["1 0 0:999 / / rw - ext4 root rw"])
        with pytest.raises(PrivateArtifactError) as excinfo:
            mount.admit_fd_mount(fd)
    finally:
        os.close(fd)
    assert excinfo.value.code == "UNSUPPORTED_FS"


def test_mount_admission_refuses_unsafe_fstype_for_opened_fd(monkeypatch, tmp_path):
    import harness.private_artifact_fs_mount as mount

    if not mount.supported():
        pytest.skip("mountinfo admission unavailable")
    fd = _fd_for(tmp_path)
    try:
        dev = _device_pair(fd)
        monkeypatch.setattr(mount, "_mountinfo_lines", lambda: [f"1 0 {dev} / / rw - 9p D: rw"])
        with pytest.raises(PrivateArtifactError) as excinfo:
            mount.admit_fd_mount(fd)
    finally:
        os.close(fd)
    assert excinfo.value.code == "UNSUPPORTED_FS"


def test_mount_admission_refuses_unsafe_fstatfs_magic(monkeypatch, tmp_path):
    import harness.private_artifact_fs_mount as mount

    if not mount.supported():
        pytest.skip("mountinfo admission unavailable")
    fd = _fd_for(tmp_path)
    try:
        dev = _device_pair(fd)
        monkeypatch.setattr(mount, "_fstatfs_magic", lambda _fd: 0x01021997)
        monkeypatch.setattr(mount, "_mountinfo_lines", lambda: [f"1 0 {dev} / / rw - ext4 root rw"])
        with pytest.raises(PrivateArtifactError) as excinfo:
            mount.admit_fd_mount(fd)
    finally:
        os.close(fd)
    assert excinfo.value.code == "UNSUPPORTED_FS"


def test_read_leaf_fd_mount_admission_runs_before_body_io(monkeypatch, tmp_path):
    import harness.private_artifact_fs_posix as backend

    if not backend.supported():
        pytest.skip("POSIX private artifact backend unavailable")
    root = tmp_path / "root"
    root.mkdir()
    (root / "payload.bin").write_bytes(b"value")
    original = backend._admit_fd_mount

    def fail_leaf(fd: int) -> None:
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            raise PrivateArtifactError("UNSUPPORTED_FS")
        original(fd)

    with open_artifact_root(root, writable=False) as fs:
        monkeypatch.setattr(backend, "_admit_fd_mount", fail_leaf)
        with pytest.raises(PrivateArtifactError) as excinfo:
            fs.read_bytes("payload.bin", max_bytes=8)
    assert excinfo.value.code == "UNSUPPORTED_FS"


def test_write_temp_fd_mount_admission_runs_before_publication(monkeypatch, tmp_path):
    import harness.private_artifact_fs_posix as backend

    if not backend.supported():
        pytest.skip("POSIX private artifact backend unavailable")
    root = tmp_path / "root"
    root.mkdir()
    original = backend._admit_fd_mount

    def fail_leaf(fd: int) -> None:
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            raise PrivateArtifactError("UNSUPPORTED_FS")
        original(fd)

    with open_artifact_root(root) as fs:
        monkeypatch.setattr(backend, "_admit_fd_mount", fail_leaf)
        with pytest.raises(PrivateArtifactError) as excinfo:
            fs.write_new_or_same("payload.bin", b"value")
    assert excinfo.value.code == "UNSUPPORTED_FS"
    assert not (root / "payload.bin").exists()
