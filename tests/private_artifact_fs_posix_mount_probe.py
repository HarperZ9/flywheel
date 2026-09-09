"""Stdlib POSIX mount-semantics probe for private_artifact_fs.

Run on WSL with:
    PYTHONPATH=. python3 tests/private_artifact_fs_posix_mount_probe.py
"""
from __future__ import annotations

import argparse
import os
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
from harness.private_artifact_fs_posix_tail import borrowed_descriptor


UNSUPPORTED_FS = "UNSUPPORTED_FS"


def _expect_code(fn, code: str) -> None:
    try:
        fn()
    except PrivateArtifactError as exc:
        assert exc.code == code, exc.code
        return
    raise AssertionError(f"expected {code}")


def _decode_mount_path(value: str) -> str:
    return value.replace("\\040", " ").replace("\\011", "\t").replace("\\012", "\n")


def _mount_fstype(path: Path) -> str:
    target = str(path.resolve())
    best: tuple[int, str] | None = None
    for line in Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines():
        before, after = line.split(" - ", 1)
        fields = before.split()
        if len(fields) < 5:
            continue
        mountpoint = _decode_mount_path(fields[4])
        if target == mountpoint or target.startswith(mountpoint.rstrip("/") + "/"):
            fstype = after.split()[0]
            if best is None or len(mountpoint) > best[0]:
                best = (len(mountpoint), fstype)
    if best is None:
        raise AssertionError(f"no mountinfo entry for {target}")
    return best[1]


def _root_under(parent: Path, prefix: str) -> Path:
    base = Path(tempfile.mkdtemp(prefix=prefix, dir=str(parent)))
    root = base / "root"
    root.mkdir()
    (root / "payload.bin").write_bytes(b"ORIGINAL-OWNED-CANARY")
    return root


def _exercise_native_descriptor_retention(native_parent: Path) -> None:
    root = _root_under(native_parent, "fw-pafs-native-")
    base = root.parent
    replacement = base / "replacement"
    replacement.mkdir()
    (replacement / "payload.bin").write_bytes(b"REPLACEMENT-CANARY")
    try:
        assert _mount_fstype(root) not in {"9p", "drvfs"}
        expected = root_identity(root)
        with open_artifact_root(root, expected=expected, writable=False) as fs:
            with fs.borrow_descriptor() as borrowed:
                old_root = base / "old-root"
                root.rename(old_root)
                replacement.rename(root)
                child = os.open("payload.bin", os.O_RDONLY, dir_fd=borrowed.fd)
                try:
                    assert os.read(child, 128) == b"ORIGINAL-OWNED-CANARY"
                finally:
                    os.close(child)
                _expect_code(lambda: fs.read_bytes("payload.bin", max_bytes=128), "UNSAFE_PATH")
    finally:
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(base / "old-root", ignore_errors=True)
        shutil.rmtree(base, ignore_errors=True)


def _borrow_raw_9p_fd(root: Path) -> None:
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0))
    try:
        st = os.fstat(fd)
        expected = ArtifactIdentity("posix", int(st.st_dev), int(st.st_ino))
        manager = borrowed_descriptor(fd, expected)
        try:
            borrowed = manager.__enter__()
        except PrivateArtifactError:
            raise
        else:
            manager.close()
            if borrowed.fd is not None:
                try:
                    os.fstat(borrowed.fd)
                except OSError:
                    pass
                else:
                    os.close(borrowed.fd)
            raise AssertionError("unsafe raw 9p borrowed descriptor admitted")
    finally:
        os.close(fd)


def _exercise_9p_refusal(windows_parent: Path) -> None:
    root = _root_under(windows_parent, "fw-pafs-9p-")
    try:
        assert _mount_fstype(root) in {"9p", "drvfs"}
        _expect_code(lambda: root_identity(root), UNSUPPORTED_FS)
        _expect_code(lambda: open_artifact_root(root, writable=False).__enter__(), UNSUPPORTED_FS)
        _expect_code(lambda: open_artifact_root(root, writable=True).__enter__(), UNSUPPORTED_FS)
        _expect_code(lambda: _borrow_raw_9p_fd(root), UNSUPPORTED_FS)
    finally:
        shutil.rmtree(root.parent, ignore_errors=True)


def _exercise_leaf_fd_admission(native_parent: Path) -> None:
    import harness.private_artifact_fs_posix as backend

    root = _root_under(native_parent, "fw-pafs-leaf-")
    original = backend._admit_fd_mount
    try:
        with open_artifact_root(root) as fs:
            def fail_leaf(fd: int) -> None:
                mode = os.fstat(fd).st_mode
                if not stat.S_ISDIR(mode):
                    raise PrivateArtifactError(UNSUPPORTED_FS)
                original(fd)

            backend._admit_fd_mount = fail_leaf
            _expect_code(lambda: fs.read_bytes("payload.bin", max_bytes=128), UNSUPPORTED_FS)
            _expect_code(lambda: fs.write_new_or_same("new.bin", b"new"), UNSUPPORTED_FS)
            assert not (root / "new.bin").exists()
    finally:
        backend._admit_fd_mount = original
        shutil.rmtree(root.parent, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-parent", default="/tmp")
    parser.add_argument("--windows-parent", default="/mnt/d/Temp")
    args = parser.parse_args()
    if os.name == "nt":
        raise AssertionError("this probe must run on POSIX")
    assert supported(), "private artifact POSIX backend unsupported"
    native_parent = Path(args.native_parent)
    windows_parent = Path(args.windows_parent)
    assert native_parent.is_dir() and os.access(native_parent, os.W_OK)
    assert windows_parent.is_dir() and os.access(windows_parent, os.W_OK)
    _exercise_native_descriptor_retention(native_parent)
    _exercise_9p_refusal(windows_parent)
    _exercise_leaf_fd_admission(native_parent)
    print("posix private artifact mount probe passed")


if __name__ == "__main__":
    main()
