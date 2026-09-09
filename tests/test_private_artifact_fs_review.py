from __future__ import annotations

import errno
import json
import os
from pathlib import Path

import pytest
from harness.private_artifact_fs import (
    ArtifactIdentity,
    PrivateArtifactError,
    open_artifact_root,
    root_identity,
    supported,
)


def _assert_code(excinfo, code: str) -> None:
    assert excinfo.value.code == code


@pytest.mark.skipif(not supported(), reason="private artifact backend unsupported")
def test_missing_root_is_typed_not_found(tmp_path):
    missing = tmp_path / "missing-root"
    with pytest.raises(PrivateArtifactError) as excinfo:
        root_identity(missing)
    _assert_code(excinfo, "NOT_FOUND")
    with pytest.raises(PrivateArtifactError) as excinfo:
        with open_artifact_root(missing):
            pass
    _assert_code(excinfo, "NOT_FOUND")


@pytest.mark.skipif(not supported(), reason="private artifact backend unsupported")
def test_artifact_identity_has_stable_json_shape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    identity = root_identity(root)
    encoded = json.loads(json.dumps(identity.to_json_dict(), sort_keys=True))
    assert set(encoded) == {"platform", "device", "inode"}
    assert ArtifactIdentity.from_json_dict(encoded) == identity


@pytest.mark.skipif(not supported(), reason="private artifact backend unsupported")
def test_context_close_is_idempotent_and_reuse_is_typed(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    fs = open_artifact_root(root).__enter__()
    fs.close()
    fs.close()
    with pytest.raises(PrivateArtifactError) as excinfo:
        fs.read_bytes("payload.bin", max_bytes=1)
    _assert_code(excinfo, "CLOSED")


@pytest.mark.skipif(not supported(), reason="private artifact backend unsupported")
def test_readonly_authority_refuses_publication(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    with open_artifact_root(root, writable=False) as fs:
        with pytest.raises(PrivateArtifactError) as excinfo:
            fs.write_new_or_same("payload.bin", b"x")
    _assert_code(excinfo, "BUSY")


@pytest.mark.skipif(not supported(), reason="private artifact backend unsupported")
def test_partial_temp_write_failure_leaves_no_private_bytes(monkeypatch, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    if os.name == "nt":
        import harness.private_artifact_fs_windows as backend
        original = backend._win.write_file

        def partial(handle, data):
            original(handle, b"zz")
            raise OSError(errno.EIO, "synthetic partial write")

        monkeypatch.setattr(backend._win, "write_file", partial)
    else:
        import harness.private_artifact_fs_posix as backend
        original = backend._write_all

        def partial(fd, data):
            os.write(fd, b"zz")
            raise OSError(errno.EIO, "synthetic partial write")

        monkeypatch.setattr(backend, "_write_all", partial)
    with open_artifact_root(root) as fs:
        with pytest.raises(PrivateArtifactError) as excinfo:
            fs.write_new_or_same("payload.bin", b"secret")
    _assert_code(excinfo, "IO_ERROR")
    assert list(root.iterdir()) == []


@pytest.mark.skipif(os.name == "nt" or not supported(), reason="POSIX descriptor publication control")
def test_posix_publication_source_stays_bound_to_owned_object(monkeypatch, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
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

    monkeypatch.setattr(backend, "_replace_temp", replace_after_name_swap)
    with open_artifact_root(root) as fs:
        assert fs.write_new_or_same("payload.bin", b"RIGHT") == "created"
    assert (root / "payload.bin").read_bytes() == b"RIGHT"


@pytest.mark.skipif(os.name == "nt" or not supported(), reason="POSIX fd leak control")
def test_posix_parent_chain_failure_releases_partial_descendants(tmp_path):
    proc_fd = Path("/proc/self/fd")
    if not proc_fd.exists():
        pytest.skip("/proc fd accounting unavailable")
    root = tmp_path / "root"
    (root / "aa" / "bb").mkdir(parents=True)
    before = len(list(proc_fd.iterdir()))
    with open_artifact_root(root) as fs:
        with pytest.raises(PrivateArtifactError) as excinfo:
            fs.read_bytes("aa/bb/missing/x", max_bytes=1)
    _assert_code(excinfo, "NOT_FOUND")
    assert len(list(proc_fd.iterdir())) <= before


@pytest.mark.skipif(os.name != "nt" or not supported(), reason="Windows handle controls")
def test_windows_parent_chain_failure_releases_partial_descendants(tmp_path):
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    count = wintypes.DWORD()
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetProcessHandleCount.restype = wintypes.BOOL

    def handle_count() -> int:
        if not kernel32.GetProcessHandleCount(kernel32.GetCurrentProcess(), ctypes.byref(count)):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(count.value)

    root = tmp_path / "root"
    (root / "aa" / "bb").mkdir(parents=True)
    before = handle_count()
    with open_artifact_root(root) as fs:
        with pytest.raises(PrivateArtifactError) as excinfo:
            fs.read_bytes("aa/bb/missing/x", max_bytes=1)
    _assert_code(excinfo, "NOT_FOUND")
    assert handle_count() <= before + 1


@pytest.mark.skipif(os.name != "nt" or not supported(), reason="Windows UTF-16 name control")
def test_windows_utf16_non_bmp_names_and_lone_surrogates(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    name = "emoji\U0001f600.bin"
    bad = "bad" + chr(0xD800) + ".bin"
    with open_artifact_root(root) as fs:
        assert fs.write_new_or_same(name, b"value") == "created"
        assert fs.read_bytes(name, max_bytes=5) == b"value"
        assert fs.write_new_or_same(name, b"value") == "idempotent"
        with pytest.raises(PrivateArtifactError) as excinfo:
            fs.write_new_or_same(name, b"other")
        _assert_code(excinfo, "CONFLICT")
        with pytest.raises(PrivateArtifactError) as excinfo:
            fs.write_new_or_same(bad, b"x")
        _assert_code(excinfo, "UNSAFE_PATH")


@pytest.mark.skipif(os.name != "nt" or not supported(), reason="Windows directory sharing control")
def test_windows_existing_directory_writer_gets_typed_busy(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    import harness.private_artifact_fs_windows as backend

    handle = backend._win.create_file(
        str(root),
        backend._win.DELETE | backend._win.SYNCHRONIZE,
        backend._win.FILE_SHARE_READ | backend._win.FILE_SHARE_WRITE | backend._win.FILE_SHARE_DELETE,
        backend._win.OPEN_EXISTING,
        backend._win.FILE_FLAG_BACKUP_SEMANTICS | backend._win.FILE_FLAG_OPEN_REPARSE_POINT,
    )
    try:
        with pytest.raises(PrivateArtifactError) as excinfo:
            with open_artifact_root(root):
                pass
    finally:
        backend._win.close_handle(handle)
    _assert_code(excinfo, "BUSY")


@pytest.mark.skipif(os.name != "nt" or not supported(), reason="Windows handle reuse control")
def test_windows_transferred_temp_handle_is_not_reclosed_after_reuse(monkeypatch, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    innocent_path = tmp_path / "innocent.bin"; innocent_path.write_bytes(b"safe")
    import harness.private_artifact_fs_windows as backend

    original_replace = backend._replace_temp
    original_read = backend._read_at
    state: dict[str, int] = {}

    def remember_temp(parent, handle, name):
        state["temp"] = handle
        return original_replace(parent, handle, name)

    def open_innocent_then_fail(chain, name, max_bytes):
        if "temp" not in state: return original_read(chain, name, max_bytes)
        target = state.get("temp")
        held: list[int] = []
        chosen: int | None = None
        try:
            for _attempt in range(1024):
                handle = backend._win.create_file(
                    str(innocent_path),
                    backend._win.GENERIC_READ | backend._win.SYNCHRONIZE,
                    backend._win.FILE_SHARE_READ | backend._win.FILE_SHARE_WRITE | backend._win.FILE_SHARE_DELETE,
                    backend._win.OPEN_EXISTING,
                    backend._win.FILE_FLAG_OPEN_REPARSE_POINT,
                )
                if handle == target:
                    chosen = handle
                    break
                held.append(handle)
            if chosen is None and held:
                chosen = held.pop()
            state["innocent"] = chosen if chosen is not None else -1
        finally:
            for handle in held:
                backend._win.close_handle(handle)
        raise PrivateArtifactError("IO_ERROR")

    monkeypatch.setattr(backend, "_replace_temp", remember_temp)
    monkeypatch.setattr(backend, "_read_at", open_innocent_then_fail)
    reused = False
    try:
        for index in range(64):
            state.clear()
            with open_artifact_root(root) as fs:
                with pytest.raises(PrivateArtifactError):
                    fs.write_new_or_same(f"payload-{index}.bin", b"x")
            innocent = state.get("innocent")
            if innocent is None:
                continue
            try:
                if innocent == state.get("temp"):
                    backend._win.handle_info(innocent)
                    reused = True
                    break
            finally:
                try:
                    backend._win.close_handle(innocent)
                except OSError:
                    pass
    finally:
        monkeypatch.setattr(backend, "_replace_temp", original_replace)
        monkeypatch.setattr(backend, "_read_at", original_read)
    if not reused:
        pytest.skip("Windows did not reuse the transferred handle value in this run")


@pytest.mark.skipif(os.name != "nt" or not supported(), reason="Windows readonly sharing control")
def test_windows_readonly_authority_denies_directory_write_and_delete(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    import harness.private_artifact_fs_windows as backend
    from harness.private_artifact_fs_windows_tail import is_sharing

    with open_artifact_root(root, writable=False):
        for access in (backend._win.GENERIC_WRITE, backend._win.DELETE):
            with pytest.raises(OSError) as excinfo:
                backend._win.create_file(
                    str(root),
                    access | backend._win.SYNCHRONIZE,
                    backend._win.FILE_SHARE_READ | backend._win.FILE_SHARE_WRITE | backend._win.FILE_SHARE_DELETE,
                    backend._win.OPEN_EXISTING,
                    backend._win.FILE_FLAG_BACKUP_SEMANTICS | backend._win.FILE_FLAG_OPEN_REPARSE_POINT,
                )
            assert is_sharing(excinfo.value)


def test_public_plan_omits_private_scratch_paths():
    doc = Path(__file__).resolve().parents[1] / "docs" / "superpowers" / "plans" / "2026-09-08-private-artifact-fs.md"
    text = doc.read_text(encoding="utf-8")
    forbidden = ["C:/dev/" + ".scratch", "PRIVATE-ARTIFACT-FS-" + "INDEPENDENT", "SOURCE-CONTEXT-" + "B7FC"]
    assert not any(token in text for token in forbidden)
