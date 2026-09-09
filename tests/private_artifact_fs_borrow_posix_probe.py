from __future__ import annotations

import os
import errno
import shutil
import tempfile
from pathlib import Path

from harness.private_artifact_fs import PrivateArtifactError, open_artifact_root, root_identity, supported


def _expect_code(fn, code: str) -> None:
    try:
        fn()
    except PrivateArtifactError as exc:
        assert exc.code == code, exc.code
        return
    raise AssertionError(f"expected {code}")


def _identity_from_fd(fd: int):
    from harness.private_artifact_fs import ArtifactIdentity
    st = os.fstat(fd)
    return ArtifactIdentity("posix", int(st.st_dev), int(st.st_ino))


def _exercise_shape_and_lifetime(root: Path) -> None:
    (root / "payload.bin").write_bytes(b"value")
    expected = root_identity(root)
    with open_artifact_root(root, expected=expected, writable=False) as fs:
        assert fs.identity == expected
        with fs.borrow_descriptor() as borrowed:
            fd = borrowed.fd
            assert borrowed.platform == "posix"
            assert borrowed.handle is None and fd is not None
            assert borrowed.identity == expected == _identity_from_fd(fd)
        try:
            os.fstat(fd)
        except OSError:
            pass
        else:
            os.close(fd)
            raise AssertionError("borrowed fd remained open after context")
        assert fs.read_bytes("payload.bin", max_bytes=5) == b"value"
    _expect_code(lambda: fs.identity, "CLOSED")
    _expect_code(lambda: fs.borrow_descriptor().__enter__(), "CLOSED")


def _exercise_no_path_reopen(root: Path, base: Path) -> None:
    replacement = base / "replacement"
    replacement.mkdir()
    (replacement / "payload.bin").write_bytes(b"replacement")
    with open_artifact_root(root, writable=False) as fs:
        retained = fs.identity
        with fs.borrow_descriptor() as borrowed:
            fd = borrowed.fd
            old = base / "old-root"
            root.rename(old)
            replacement.rename(root)
            assert fs.identity == retained
            child = os.open("payload.bin", os.O_RDONLY, dir_fd=fd)
            try:
                assert os.read(child, 64) == b"value"
            finally:
                os.close(child)
        _expect_code(lambda: fs.read_bytes("payload.bin", max_bytes=64), "UNSAFE_PATH")


def _exercise_mismatch_cleanup(root: Path, base: Path) -> None:
    import harness.private_artifact_fs_posix_tail as tail

    other = base / "other"
    other.mkdir()
    other_fd = os.open(other, os.O_RDONLY | os.O_DIRECTORY)
    made: list[int] = []
    original = tail.duplicate_fd

    def wrong_dup(_fd: int) -> int:
        dup = os.dup(other_fd)
        made.append(dup)
        return dup

    tail.duplicate_fd = wrong_dup
    try:
        with open_artifact_root(root, writable=False) as fs:
            _expect_code(lambda: fs.borrow_descriptor().__enter__(), "UNSAFE_PATH")
    finally:
        tail.duplicate_fd = original
        os.close(other_fd)
    assert made
    try:
        os.fstat(made[-1])
    except OSError:
        pass
    else:
        os.close(made[-1])
        raise AssertionError("wrong borrowed fd leaked")


def _exercise_unsupported_duplicate(root: Path) -> None:
    import harness.private_artifact_fs_posix_tail as tail

    original = tail.os.dup
    delattr(tail.os, "dup")
    try:
        with open_artifact_root(root, writable=False) as fs:
            _expect_code(lambda: fs.borrow_descriptor().__enter__(), "UNSUPPORTED_OS")
    finally:
        tail.os.dup = original


def _exercise_set_inheritable_cleanup(root: Path) -> None:
    import harness.private_artifact_fs_posix_tail as tail

    original = tail.os.set_inheritable
    made: list[int] = []

    def fail_setup(fd: int, inheritable: bool) -> None:
        made.append(fd)
        raise OSError(errno.EIO, "synthetic close-on-exec failure")

    tail.os.set_inheritable = fail_setup
    try:
        with open_artifact_root(root, writable=False) as fs:
            _expect_code(lambda: fs.borrow_descriptor().__enter__(), "IO_ERROR")
            assert fs.read_bytes("payload.bin", max_bytes=5) == b"value"
    finally:
        tail.os.set_inheritable = original
    assert made
    try:
        os.fstat(made[-1])
    except OSError:
        pass
    else:
        os.close(made[-1])
        raise AssertionError("duplicate fd leaked after set_inheritable failure")


def _exercise_reentry_refusal(root: Path) -> None:
    import harness.private_artifact_fs_posix_tail as tail

    original = tail.duplicate_fd
    made: list[int] = []

    def record_dup(fd: int) -> int:
        dup = original(fd)
        made.append(dup)
        return dup

    tail.duplicate_fd = record_dup
    try:
        with open_artifact_root(root, writable=False) as fs:
            manager = fs.borrow_descriptor()
            first = manager.__enter__()
            _expect_code(lambda: manager.__enter__(), "BUSY")
            assert made == [first.fd]
            manager.close()
            try:
                os.fstat(first.fd)
            except OSError:
                pass
            else:
                os.close(first.fd)
                raise AssertionError("borrowed fd remained open")
            _expect_code(lambda: manager.__enter__(), "CLOSED")
            assert made == [first.fd]
    finally:
        tail.duplicate_fd = original


def main() -> None:
    assert supported(), "POSIX backend unsupported"
    base = Path(tempfile.mkdtemp(prefix="fw_pafs_borrow_"))
    try:
        root = base / "root"
        root.mkdir()
        _exercise_shape_and_lifetime(root)
        _exercise_no_path_reopen(root, base)
        _exercise_mismatch_cleanup(base / "old-root", base)
        _exercise_unsupported_duplicate(base / "old-root")
        _exercise_set_inheritable_cleanup(base / "old-root")
        _exercise_reentry_refusal(base / "old-root")
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print("posix private artifact borrow probe passed")


if __name__ == "__main__":
    main()
