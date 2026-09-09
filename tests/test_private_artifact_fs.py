from __future__ import annotations
import errno
import os
import shutil
import subprocess
import sys
from pathlib import Path
import pytest
from harness.private_artifact_fs import (
    PrivateArtifactError,
    open_artifact_root,
    root_identity,
    supported,
)
def _assert_code(excinfo, code: str) -> None:
    assert excinfo.value.code == code
def _replace_dir_with_dir(path: Path, replacement: Path) -> bool:
    old = path.with_name(path.name + "-old")
    try:
        path.rename(old)
        replacement.rename(path)
        return True
    except PermissionError:
        return False
def _make_dir_reparse(link: Path, target: Path) -> bool:
    target.mkdir(parents=True, exist_ok=True)
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(target)],
                check=False,
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        link.symlink_to(target, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        return False
def _remove_reparse(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        pass
def test_api_reports_typed_unsupported_when_backend_is_missing(monkeypatch, tmp_path):
    # Break caught: unsupported platforms are treated as usable and then fall
    # through into ordinary path I/O.
    from harness import private_artifact_fs
    monkeypatch.setattr(private_artifact_fs, "_backend", lambda: None)
    with pytest.raises(PrivateArtifactError) as excinfo:
        root_identity(tmp_path)
    _assert_code(excinfo, "UNSUPPORTED_OS")
@pytest.mark.skipif(not supported(), reason="private artifact backend unsupported")
def test_replacing_the_root_during_context_is_rejected_before_outside_read(tmp_path):
    # Break caught: above-root swaps redirect a later path read to outside bytes.
    root = tmp_path / "state" / "artifacts"
    (root / "owner").mkdir(parents=True)
    (root / "owner" / "payload.txt").write_bytes(b"inside")
    outside_root = tmp_path / "outside-root"
    (outside_root / "owner").mkdir(parents=True)
    (outside_root / "owner" / "payload.txt").write_bytes(b"OUTSIDE RACE CANARY")
    expected = root_identity(root)
    with open_artifact_root(root, expected=expected) as fs:
        if not _replace_dir_with_dir(root, outside_root):
            assert fs.read_bytes("owner/payload.txt", max_bytes=64) == b"inside"
            return
        with pytest.raises(PrivateArtifactError) as excinfo:
            fs.read_bytes("owner/payload.txt", max_bytes=64)
    _assert_code(excinfo, "UNSAFE_PATH")
@pytest.mark.skipif(not supported(), reason="private artifact backend unsupported")
def test_descendant_reparse_parent_cannot_redirect_reads(tmp_path):
    # Break caught: a validated descendant directory is swapped to a junction or
    # symlink before the read and returns an outside canary.
    root = tmp_path / "root"
    inside = root / "owner"
    inside.mkdir(parents=True)
    (inside / "payload.txt").write_bytes(b"inside")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "payload.txt").write_bytes(b"OUTSIDE DESCENDANT CANARY")
    shutil.rmtree(inside)
    if not _make_dir_reparse(inside, outside):
        pytest.skip("directory reparse creation unavailable")
    try:
        with open_artifact_root(root) as fs:
            with pytest.raises(PrivateArtifactError) as excinfo:
                fs.read_bytes("owner/payload.txt", max_bytes=64)
    finally:
        _remove_reparse(inside)
    _assert_code(excinfo, "UNSAFE_PATH")
@pytest.mark.skipif(not supported(), reason="private artifact backend unsupported")
def test_reparse_leaf_cannot_be_read_as_artifact_bytes(tmp_path):
    # Break caught: a leaf symlink/reparse point is followed after admission.
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"OUTSIDE LEAF CANARY")
    leaf = root / "payload.txt"
    try:
        leaf.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("file symlink creation unavailable")
    with open_artifact_root(root) as fs:
        with pytest.raises(PrivateArtifactError) as excinfo:
            fs.read_bytes("payload.txt", max_bytes=64)
    _assert_code(excinfo, "UNSAFE_PATH")
@pytest.mark.skipif(not supported(), reason="private artifact backend unsupported")
def test_directory_leaf_is_not_accepted_as_artifact_bytes(tmp_path):
    # Break caught: a directory leaf is treated as a readable artifact.
    root = tmp_path / "root"
    (root / "payload.bin").mkdir(parents=True)
    with open_artifact_root(root) as fs:
        with pytest.raises(PrivateArtifactError) as excinfo:
            fs.read_bytes("payload.bin", max_bytes=64)
    _assert_code(excinfo, "NOT_REGULAR")
@pytest.mark.skipif(not supported(), reason="private artifact backend unsupported")
def test_read_rejects_large_file_before_returning_bytes(tmp_path):
    # Break caught: max_bytes is checked after allocating the whole file.
    root = tmp_path / "root"
    root.mkdir()
    (root / "payload.bin").write_bytes(b"x" * 524_288)
    with open_artifact_root(root) as fs:
        with pytest.raises(PrivateArtifactError) as excinfo:
            fs.read_bytes("payload.bin", max_bytes=32)
    _assert_code(excinfo, "TOO_LARGE")
@pytest.mark.skipif(os.name == "nt" or not supported(), reason="POSIX mutation control")
@pytest.mark.parametrize("mode", ["grow", "shrink"])
def test_posix_read_rejects_file_size_drift_after_open(monkeypatch, tmp_path, mode):
    # Break caught: a file grows or shrinks after the pre-read size check and
    # the opened descriptor's changed bytes are still returned as valid.
    root = tmp_path / "root"
    root.mkdir()
    target = root / "payload.bin"
    target.write_bytes(b"abc")
    import harness.private_artifact_fs_posix as backend
    original = backend._read_fd_bounded
    def mutate_then_read(fd, max_bytes):
        path = Path(os.readlink(f"/proc/self/fd/{fd}"))
        writer = os.open(path, os.O_WRONLY)
        try:
            if mode == "grow":
                os.lseek(writer, 0, os.SEEK_END)
                os.write(writer, b"def")
            else:
                os.ftruncate(writer, 1)
        finally:
            os.close(writer)
        return original(fd, max_bytes)
    monkeypatch.setattr(backend, "_read_fd_bounded", mutate_then_read)
    with open_artifact_root(root) as fs:
        with pytest.raises(PrivateArtifactError) as excinfo:
            fs.read_bytes("payload.bin", max_bytes=16)
    _assert_code(excinfo, "IO_ERROR")
@pytest.mark.skipif(not supported(), reason="private artifact backend unsupported")
def test_write_new_or_same_is_exact_byte_idempotent_and_conflicting(tmp_path):
    # Break caught: content-addressed publication overwrites different bytes.
    root = tmp_path / "root"
    root.mkdir()
    with open_artifact_root(root) as fs:
        assert fs.write_new_or_same("aa/payload.bin", b"one") == "created"
        assert fs.write_new_or_same("aa/payload.bin", b"one") == "idempotent"
        with pytest.raises(PrivateArtifactError) as excinfo:
            fs.write_new_or_same("aa/payload.bin", b"two")
    _assert_code(excinfo, "CONFLICT")
    assert (root / "aa" / "payload.bin").read_bytes() == b"one"
@pytest.mark.skipif(not supported(), reason="private artifact backend unsupported")
def test_replacing_the_root_during_context_is_rejected_before_outside_write(tmp_path):
    # Break caught: above-root swaps redirect publication outside the admitted
    # root after the caller has captured root identity.
    root = tmp_path / "state" / "artifacts"
    root.mkdir(parents=True)
    outside_root = tmp_path / "outside-root"
    outside_root.mkdir()
    expected = root_identity(root)
    with open_artifact_root(root, expected=expected) as fs:
        if not _replace_dir_with_dir(root, outside_root):
            assert fs.write_new_or_same("owner/payload.bin", b"secret") == "created"
            assert (root / "owner" / "payload.bin").read_bytes() == b"secret"
            return
        with pytest.raises(PrivateArtifactError) as excinfo:
            fs.write_new_or_same("owner/payload.bin", b"secret")
    _assert_code(excinfo, "UNSAFE_PATH")
    assert not (root / "owner" / "payload.bin").exists()
@pytest.mark.skipif(not supported(), reason="private artifact backend unsupported")
def test_parent_creation_refuses_reparse_escape_and_leaves_outside_clean(tmp_path):
    # Break caught: parent creation follows a newly supplied descendant reparse
    # point and writes the payload outside the root.
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    link = root / "owner"
    if not _make_dir_reparse(link, outside):
        pytest.skip("directory reparse creation unavailable")
    try:
        with open_artifact_root(root) as fs:
            with pytest.raises(PrivateArtifactError) as excinfo:
                fs.write_new_or_same("owner/payload.bin", b"secret")
    finally:
        _remove_reparse(link)
    _assert_code(excinfo, "UNSAFE_PATH")
    assert not (outside / "payload.bin").exists()
@pytest.mark.skipif(not supported(), reason="private artifact backend unsupported")
def test_parent_created_then_swapped_to_reparse_is_rejected(monkeypatch, tmp_path):
    # Break caught: a missing parent is created, swapped to a reparse point, and
    # then opened by path for the final write.
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    if not _make_dir_reparse(tmp_path / "probe-link", outside):
        pytest.skip("directory reparse creation unavailable")
    _remove_reparse(tmp_path / "probe-link")
    if os.name == "nt":
        import harness.private_artifact_fs_windows as backend
    else:
        import harness.private_artifact_fs_posix as backend
    original = backend._mkdir
    def mkdir_then_swap(parent, name, *args):
        original(parent, name, *args)
        created = parent.path / name
        try:
            shutil.rmtree(created)
        except PermissionError as exc:
            raise PrivateArtifactError("UNSAFE_PATH") from exc
        assert _make_dir_reparse(created, outside)
    monkeypatch.setattr(backend, "_mkdir", mkdir_then_swap)
    try:
        with open_artifact_root(root) as fs:
            with pytest.raises(PrivateArtifactError) as excinfo:
                fs.write_new_or_same("owner/payload.bin", b"secret")
    finally:
        monkeypatch.setattr(backend, "_mkdir", original)
        _remove_reparse(root / "owner")
    _assert_code(excinfo, "UNSAFE_PATH")
    assert not (outside / "payload.bin").exists()
@pytest.mark.skipif(os.name != "nt" or not supported(), reason="Windows sharing control")
def test_existing_writable_handle_blocks_immutable_publication(tmp_path):
    # Break caught: a final artifact is accepted while another handle can still
    # mutate it during the comparison window.
    root = tmp_path / "root"
    root.mkdir()
    target = root / "payload.bin"
    target.write_bytes(b"stable")
    handle = open(target, "r+b")
    try:
        with open_artifact_root(root) as fs:
            with pytest.raises(PrivateArtifactError) as excinfo:
                fs.write_new_or_same("payload.bin", b"stable")
    finally:
        handle.close()
    _assert_code(excinfo, "CONFLICT")
@pytest.mark.skipif(not supported(), reason="private artifact backend unsupported")
def test_failed_publish_removes_only_its_owned_temp(monkeypatch, tmp_path):
    # Break caught: interrupted publication leaves a partial final file or
    # recursively cleans unrelated files from the parent directory.
    root = tmp_path / "root"
    root.mkdir()
    (root / "keep.tmp").write_bytes(b"keep")
    import harness.private_artifact_fs_posix as posix_backend
    if os.name == "nt":
        import harness.private_artifact_fs_windows as backend
    else:
        backend = posix_backend
    original = backend._replace_temp
    def fail_once(*args, **kwargs):
        raise OSError(errno.EIO, "simulated interruption")
    monkeypatch.setattr(backend, "_replace_temp", fail_once)
    with open_artifact_root(root) as fs:
        with pytest.raises(PrivateArtifactError) as excinfo:
            fs.write_new_or_same("payload.bin", b"value")
    monkeypatch.setattr(backend, "_replace_temp", original)
    _assert_code(excinfo, "IO_ERROR")
    assert not (root / "payload.bin").exists()
    assert (root / "keep.tmp").read_bytes() == b"keep"
    assert sorted(p.name for p in root.iterdir()) == ["keep.tmp"]
