"""Stdlib POSIX probe for private_artifact_fs.

Run with:
    PYTHONPATH=. python3 tests/private_artifact_fs_posix_probe.py
"""
from __future__ import annotations

import os
import errno
import shutil
import stat
import tempfile
from pathlib import Path

from harness.private_artifact_fs import (
    ArtifactIdentity,
    PrivateArtifactError,
    open_artifact_root,
    root_identity,
    supported,
)


def _expect_code(fn, code: str) -> None:
    try:
        fn()
    except PrivateArtifactError as exc:
        assert exc.code == code, exc.code
        return
    raise AssertionError(f"expected {code}")


def _exercise_idempotence(root: Path) -> None:
    with open_artifact_root(root) as fs:
        assert fs.write_new_or_same("aa/payload.bin", b"one") == "created"
        assert fs.write_new_or_same("aa/payload.bin", b"one") == "idempotent"
        _expect_code(lambda: fs.write_new_or_same("aa/payload.bin", b"two"), "CONFLICT")
    assert stat.S_IMODE((root / "aa" / "payload.bin").stat().st_mode) == 0o600


def _exercise_missing_root(base: Path) -> None:
    missing = base / "missing-root"
    _expect_code(lambda: root_identity(missing), "NOT_FOUND")
    _expect_code(lambda: open_artifact_root(missing).__enter__(), "NOT_FOUND")


def _exercise_json_identity(root: Path) -> None:
    ident = root_identity(root)
    encoded = ident.to_json_dict()
    assert set(encoded) == {"platform", "device", "inode"}
    assert ArtifactIdentity.from_json_dict(encoded) == ident


def _exercise_closed_reuse(root: Path) -> None:
    fs = open_artifact_root(root).__enter__()
    fs.close()
    fs.close()
    _expect_code(lambda: fs.read_bytes("aa/payload.bin", max_bytes=3), "CLOSED")


def _exercise_readonly_mode(root: Path) -> None:
    with open_artifact_root(root, writable=False) as fs:
        _expect_code(lambda: fs.write_new_or_same("readonly.bin", b"x"), "BUSY")


def _exercise_partial_temp_failure(root: Path) -> None:
    import harness.private_artifact_fs_posix as backend

    original = backend._write_all

    def partial(fd: int, data: bytes) -> None:
        os.write(fd, b"zz")
        raise OSError(errno.EIO, "partial write")

    backend._write_all = partial
    try:
        with open_artifact_root(root) as fs:
            _expect_code(lambda: fs.write_new_or_same("partial.bin", b"secret"), "IO_ERROR")
    finally:
        backend._write_all = original
    assert not any(path.name.startswith(".partial.bin.") for path in root.iterdir())
    assert not (root / "partial.bin").exists()


def _exercise_descriptor_publication(root: Path) -> None:
    import harness.private_artifact_fs_posix as backend

    original = backend._replace_temp

    def replace_after_name_swap(parent, temp_or_fd, name):
        if isinstance(temp_or_fd, str):
            os.unlink(temp_or_fd, dir_fd=parent.fd)
            wrong = os.open(
                temp_or_fd,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent.fd,
            )
            try:
                os.write(wrong, b"WRONG")
                os.fsync(wrong)
            finally:
                os.close(wrong)
        return original(parent, temp_or_fd, name)

    backend._replace_temp = replace_after_name_swap
    try:
        with open_artifact_root(root) as fs:
            assert fs.write_new_or_same("descriptor.bin", b"RIGHT") == "created"
    finally:
        backend._replace_temp = original
    assert (root / "descriptor.bin").read_bytes() == b"RIGHT"


def _exercise_parent_chain_failure(root: Path) -> None:
    proc_fd = Path("/proc/self/fd")
    if not proc_fd.exists():
        return
    (root / "leak" / "aa" / "bb").mkdir(parents=True)
    before = len(list(proc_fd.iterdir()))
    with open_artifact_root(root) as fs:
        _expect_code(lambda: fs.read_bytes("leak/aa/bb/missing/x", max_bytes=1), "NOT_FOUND")
    assert len(list(proc_fd.iterdir())) <= before


def _fd_is_closed_or_close_it(fd: int, fstat) -> bool:
    try:
        fstat(fd)
    except OSError:
        return True
    os.close(fd)
    return False


def _exercise_initial_root_identity_cleanup(base: Path) -> None:
    root = base / "root-acquire-target"
    root.mkdir()
    import harness.private_artifact_fs as facade
    import harness.private_artifact_fs_posix as backend

    original_backend = facade._backend
    original_supported = backend.supported
    original_open = backend.os.open
    original_fstat = backend.os.fstat
    state: dict[str, int] = {}

    def open_record(name, flags, mode=0o777, *, dir_fd=None):
        fd = original_open(name, flags, mode, dir_fd=dir_fd)
        if name == root.name:
            state["fd"] = fd
        return fd

    def fstat_fail(fd: int):
        if fd == state.get("fd"):
            raise OSError(errno.EIO, "synthetic identity failure")
        return original_fstat(fd)

    backend.os.open = open_record
    backend.os.fstat = fstat_fail
    backend.supported = lambda: True
    facade._backend = lambda: backend
    try:
        _expect_code(lambda: root_identity(root), "IO_ERROR")
    finally:
        facade._backend = original_backend
        backend.supported = original_supported
        backend.os.open = original_open
        backend.os.fstat = original_fstat
    assert _fd_is_closed_or_close_it(state["fd"], original_fstat)


def _exercise_initial_descendant_identity_cleanup(root: Path) -> None:
    (root / "probechild").mkdir()
    import harness.private_artifact_fs_posix as backend

    original_open = backend.os.open
    original_fstat = backend.os.fstat
    state: dict[str, int] = {}

    def open_record(name, flags, mode=0o777, *, dir_fd=None):
        fd = original_open(name, flags, mode, dir_fd=dir_fd)
        if name == "probechild":
            state["fd"] = fd
        return fd

    def fstat_fail(fd: int):
        if fd == state.get("fd"):
            raise OSError(errno.EIO, "synthetic child identity failure")
        return original_fstat(fd)

    with open_artifact_root(root) as fs:
        backend.os.open = open_record
        backend.os.fstat = fstat_fail
        try:
            _expect_code(lambda: fs.read_bytes("probechild/missing.bin", max_bytes=1), "IO_ERROR")
        finally:
            backend.os.open = original_open
            backend.os.fstat = original_fstat
    assert _fd_is_closed_or_close_it(state["fd"], original_fstat)


def _exercise_bad_dir_fsync_refusal(root: Path) -> None:
    import harness.private_artifact_fs_posix as backend
    import harness.private_artifact_fs_posix_tail as tail

    original = backend._fsync_dir
    backend._fsync_dir = lambda _fd: tail.fsync_dir(1_000_000)
    try:
        with open_artifact_root(root) as fs:
            _expect_code(lambda: fs.write_new_or_same("bad-fsync.bin", b"exact"), "IO_ERROR")
    finally:
        backend._fsync_dir = original
    final = root / "bad-fsync.bin"
    if final.exists():
        assert final.read_bytes() == b"exact"


def _exercise_symlink_parent(root: Path, base: Path) -> None:
    outside = base / "outside"
    outside.mkdir()
    (outside / "payload.bin").write_bytes(b"outside")
    (root / "link").symlink_to(outside, target_is_directory=True)
    with open_artifact_root(root) as fs:
        _expect_code(lambda: fs.read_bytes("link/payload.bin", max_bytes=64), "UNSAFE_PATH")


def _exercise_size_drift(root: Path) -> None:
    target = root / "drift.bin"
    target.write_bytes(b"abc")
    import harness.private_artifact_fs_posix as backend

    original = backend._read_fd_bounded

    def mutate(fd: int, max_bytes: int) -> bytes:
        path = Path(os.readlink(f"/proc/self/fd/{fd}"))
        writer = os.open(path, os.O_WRONLY)
        try:
            os.lseek(writer, 0, os.SEEK_END)
            os.write(writer, b"def")
        finally:
            os.close(writer)
        return original(fd, max_bytes)

    backend._read_fd_bounded = mutate
    try:
        with open_artifact_root(root) as fs:
            _expect_code(lambda: fs.read_bytes("drift.bin", max_bytes=16), "IO_ERROR")
    finally:
        backend._read_fd_bounded = original


def _exercise_root_swap(root: Path, base: Path) -> None:
    expected = root_identity(root)
    replacement = base / "replacement"
    replacement.mkdir()
    with open_artifact_root(root, expected=expected) as fs:
        root.rename(base / "old-root")
        replacement.rename(root)
        _expect_code(lambda: fs.write_new_or_same("x.bin", b"outside"), "UNSAFE_PATH")


def main() -> None:
    assert supported(), "POSIX backend unsupported"
    base = Path(tempfile.mkdtemp(prefix="fw_pafs_"))
    try:
        root = base / "root"
        root.mkdir()
        _exercise_missing_root(base)
        _exercise_json_identity(root)
        _exercise_idempotence(root)
        _exercise_closed_reuse(root)
        _exercise_readonly_mode(root)
        _exercise_partial_temp_failure(root)
        _exercise_descriptor_publication(root)
        _exercise_parent_chain_failure(root)
        _exercise_initial_root_identity_cleanup(base)
        _exercise_initial_descendant_identity_cleanup(root)
        _exercise_bad_dir_fsync_refusal(root)
        _exercise_symlink_parent(root, base)
        _exercise_size_drift(root)
        _exercise_root_swap(root, base)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print("posix private artifact probe passed")


if __name__ == "__main__":
    main()
