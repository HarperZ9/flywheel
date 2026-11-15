from __future__ import annotations

from collections.abc import Iterator
import errno
import gc
import hashlib
import os
import socket
import weakref
from pathlib import Path

import pytest

import canon.concurrency_capability as concurrency_capability
import canon.concurrency_lock_backend as concurrency_lock_backend
import canon.concurrency_lock as concurrency_lock
import canon.concurrency_posix as concurrency_posix
import canon.concurrency_windows as concurrency_windows
from canon.concurrency import (
    LockError,
    RunLock,
    acquire_run_lock,
    guarded_commit,
    release_run_lock,
)
from canon.source_state import SourceStateError, SourceStateItem, source_state_sha256


def _sha(hex_char: str) -> str:
    return "sha256:" + hex_char * 64


def _swap_lock_dir_to_symlink(lock_dir: Path, displaced: Path, outside: Path) -> None:
    try:
        lock_dir.rename(displaced)
        lock_dir.symlink_to(outside, target_is_directory=True)
    except OSError:
        _restore_displaced_lock_dir(lock_dir, displaced)
        pytest.skip("current platform or privileges do not allow directory symlinks")


def _restore_displaced_lock_dir(lock_dir: Path, displaced: Path) -> None:
    if lock_dir.is_symlink():
        lock_dir.unlink()
    if displaced.exists():
        displaced.rename(lock_dir)


def _collect_garbage() -> None:
    for _ in range(3):
        gc.collect()


def _assert_lock_collected(lock_ref: weakref.ReferenceType[RunLock], owner_id: int) -> None:
    _collect_garbage()
    assert lock_ref() is None
    assert owner_id not in concurrency_capability._REGISTRY


class _WeakOwner:
    pass


class _HostileSourceStateItem(SourceStateItem):
    _malicious = {
        "path": "../escape.md",
        "sha256": "sha256:" + "B" * 64,
        "size": True,
    }

    def __getattribute__(self, name: str) -> object:
        if name in ("path", "sha256", "size") and _hostile_armed(self):
            reads = object.__getattribute__(self, "_reads")
            reads[name] = reads.get(name, 0) + 1
            threshold = {"path": 2, "sha256": 1, "size": 1}[name]
            if reads[name] > threshold:
                return self._malicious[name]
        return super().__getattribute__(name)


def _hostile_armed(item: object) -> bool:
    try:
        return object.__getattribute__(item, "_armed")
    except AttributeError:
        return False


def _hostile_source_item() -> SourceStateItem:
    item = _HostileSourceStateItem(path="a.md", sha256=_sha("a"), size=1)
    object.__setattr__(item, "_reads", {})
    object.__setattr__(item, "_armed", True)
    return item


class _HostileSourceStateTuple(tuple):
    def __new__(cls) -> "_HostileSourceStateTuple":
        return super().__new__(cls, ())

    def __init__(self) -> None:
        self._reads = 0
        self._valid = SourceStateItem(path="a.md", sha256=_sha("a"), size=1)
        self._malicious = SourceStateItem(path="b.md", sha256=_sha("b"), size=2)
        object.__setattr__(self._malicious, "path", "../escape.md")
        object.__setattr__(self._malicious, "sha256", "sha256:" + "B" * 64)
        object.__setattr__(self._malicious, "size", True)

    def __iter__(self) -> Iterator[SourceStateItem]:
        self._reads += 1
        if self._reads == 1:
            return iter((self._valid,))
        return iter((self._malicious,))


def _hostile_source_tuple() -> tuple[SourceStateItem, ...]:
    return _HostileSourceStateTuple()


def _hostile_source_digest() -> str:
    raw = (
        b'[{"path":"../escape.md","sha256":"sha256:'
        + b"B" * 64
        + b'","size":true}]\n'
    )
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def test_run_lock_conflicts_until_released(tmp_path: Path) -> None:
    first = acquire_run_lock(tmp_path, "workspace-AGENTS.md")
    try:
        with pytest.raises(LockError, match="lock-held"):
            acquire_run_lock(tmp_path, "workspace-AGENTS.md")
    finally:
        release_run_lock(first)

    second = acquire_run_lock(tmp_path, "workspace-AGENTS.md")
    release_run_lock(second)


@pytest.mark.parametrize(
    "name",
    [
        "",
        ".",
        "..",
        "../x",
        "a/b",
        "a\\b",
        "a:b",
        "a\nb",
        "CON",
        "a.",
        "caf\u00e9",
        "cafe\u0301",
        123,
    ],
)
def test_bad_lock_names_are_rejected(tmp_path: Path, name: object) -> None:
    with pytest.raises(LockError, match="invalid-lock-name"):
        acquire_run_lock(tmp_path, name)  # type: ignore[arg-type]


def test_lock_root_must_be_existing_directory(tmp_path: Path) -> None:
    file_root = tmp_path / "file-root"
    file_root.write_text("not a directory", encoding="utf-8")

    with pytest.raises(LockError, match="invalid-lock-root"):
        acquire_run_lock(file_root, "workspace")
    with pytest.raises(LockError, match="invalid-lock-root"):
        acquire_run_lock(tmp_path / "missing", "workspace")


def test_lock_root_symlink_is_rejected_before_writing_outside(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root-link"
    try:
        root.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("current platform or privileges do not allow directory symlinks")

    with pytest.raises(LockError, match="lock-reparse"):
        acquire_run_lock(root, "workspace")
    assert not (outside / ".canon-locks" / "workspace.lock").exists()


def test_lock_directory_symlink_is_rejected_before_writing_outside(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    try:
        (root / ".canon-locks").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("current platform or privileges do not allow directory symlinks")

    with pytest.raises(LockError, match="lock-reparse"):
        acquire_run_lock(root, "workspace")
    assert not (outside / "workspace.lock").exists()


def test_acquire_rejects_lock_directory_swap_after_prepare(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    real_prepare = concurrency_lock.prepare_lock_dir

    def prepare_then_swap(resolved_root: Path) -> Path:
        lock_dir = real_prepare(resolved_root)
        try:
            lock_dir.rmdir()
            lock_dir.symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("current platform or privileges do not allow directory symlinks")
        return lock_dir

    monkeypatch.setattr(concurrency_lock, "prepare_lock_dir", prepare_then_swap)

    with pytest.raises(LockError, match="lock-reparse"):
        acquire_run_lock(root, "workspace")

    assert not (outside / "workspace.lock").exists()


def test_acquire_rejects_swap_back_without_outside_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    displaced = tmp_path / "displaced-locks"
    root.mkdir()
    outside.mkdir()
    real_snapshot = concurrency_lock._lock_dir_snapshot
    real_open = os.open
    swapped = False

    def snapshot_then_swap(lock_dir: Path) -> tuple[Path, int, int]:
        nonlocal swapped
        snapshot = real_snapshot(lock_dir)
        if not swapped:
            swapped = True
            _swap_lock_dir_to_symlink(lock_dir, displaced, outside)
        return snapshot

    def open_with_swap(
        path: object,
        flags: int,
        mode: int = 0o777,
        *args: object,
        **kwargs: object,
    ) -> int:
        try:
            return real_open(path, flags, mode, *args, **kwargs)
        finally:
            lock_dir = root / ".canon-locks"
            _restore_displaced_lock_dir(lock_dir, displaced)

    monkeypatch.setattr(concurrency_lock, "_lock_dir_snapshot", snapshot_then_swap)
    monkeypatch.setattr(os, "open", open_with_swap)

    try:
        with pytest.raises(LockError, match="lock-open|lock-reparse"):
            acquire_run_lock(root, "workspace")
        assert not (outside / "workspace.lock").exists()
    finally:
        (outside / "workspace.lock").unlink(missing_ok=True)
        _restore_displaced_lock_dir(root / ".canon-locks", displaced)

    assert not (root / ".canon-locks" / "workspace.lock").exists()


def test_acquire_refuses_when_stable_parent_primitive_unavailable_before_create(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    called = False

    def fail_open(*args: object, **kwargs: object) -> int:
        nonlocal called
        called = True
        raise AssertionError("full-path os.open fallback must not be used")

    monkeypatch.setattr(concurrency_lock, "_can_use_dir_fd_lock", lambda: False)
    monkeypatch.setattr(concurrency_lock, "_can_use_windows_lock", lambda: False, raising=False)
    monkeypatch.setattr(os, "open", fail_open)

    with pytest.raises(LockError, match="lock-unsupported"):
        acquire_run_lock(tmp_path, "workspace")

    assert not called
    assert not (tmp_path / ".canon-locks" / "workspace.lock").exists()


def test_posix_lock_descriptor_remains_readable_for_release(tmp_path: Path) -> None:
    if os.name == "nt" or not concurrency_posix.supported():
        pytest.skip("POSIX descriptor readability regression")
    lock_dir = tmp_path / ".canon-locks"
    lock_dir.mkdir()
    dir_fd = concurrency_posix.open_directory(lock_dir)
    file_fd = -1
    try:
        file_fd = concurrency_posix.create_lock_file(dir_fd, "workspace.lock", "token")
        assert concurrency_posix.read_token(file_fd) == "token"
    finally:
        if file_fd >= 0:
            concurrency_posix.close_fd(file_fd)
        concurrency_posix.delete_lock_file(dir_fd, "workspace.lock")
        concurrency_posix.close_fd(dir_fd)


def test_windows_conflict_uses_stable_parent_handle_not_full_path_open(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    if os.name != "nt":
        pytest.skip("Windows stable-parent primitive regression")
    first = acquire_run_lock(tmp_path, "workspace")

    def fail_open(*args: object, **kwargs: object) -> int:
        raise AssertionError("full-path os.open fallback must not be used")

    monkeypatch.setattr(os, "open", fail_open)
    try:
        with pytest.raises(LockError, match="lock-held"):
            acquire_run_lock(tmp_path, "workspace")
        assert concurrency_capability.lookup(first) is not None
    finally:
        release_run_lock(first)


def test_windows_create_uses_delete_capable_create_new_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, int] = {}

    def fake_create(
        dir_handle: int,
        name: str,
        access: int,
        share: int,
        disposition: int,
        options: int,
    ) -> int:
        captured.update(access=access, share=share, disposition=disposition, options=options)
        return 123

    monkeypatch.setattr(concurrency_windows._api, "nt_create_relative", fake_create)
    monkeypatch.setattr(concurrency_windows, "_write_file", lambda handle, data: None)

    assert concurrency_windows.create_lock_file(7, "workspace.lock", "token") == 123
    assert captured["access"] & concurrency_windows._api.DELETE
    assert captured["share"] & concurrency_windows._api.FILE_SHARE_DELETE
    assert captured["disposition"] == concurrency_windows._api.FILE_CREATE


def test_acquire_handle_cleanup_survives_lock_directory_swap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    displaced = tmp_path / "displaced-locks"
    root.mkdir()
    outside.mkdir()

    def swap_then_fail(
        capability: object,
    ) -> None:
        _swap_lock_dir_to_symlink(capability.path.parent, displaced, outside)
        raise LockError("lock-reparse", str(capability.path))

    monkeypatch.setattr(concurrency_lock_backend, "verify_capability", swap_then_fail)

    try:
        with pytest.raises(LockError, match="lock-reparse"):
            acquire_run_lock(root, "workspace")
    finally:
        _restore_displaced_lock_dir(root / ".canon-locks", displaced)

    assert not (root / ".canon-locks" / "workspace.lock").exists()
    assert not (outside / "workspace.lock").exists()


def test_acquire_uses_real_lock_capability_after_dir_verify_swap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    displaced = tmp_path / "displaced-locks"
    root.mkdir()
    outside.mkdir()
    token = "capability-token"
    real_verify = concurrency_lock._verify_lock_dir
    calls = 0

    def verify_then_swap(lock_dir: Path, snapshot: tuple[Path, int, int]) -> None:
        nonlocal calls
        real_verify(lock_dir, snapshot)
        calls += 1
        if calls == 2:
            _swap_lock_dir_to_symlink(lock_dir, displaced, outside)
            (outside / "workspace.lock").write_text("outside-token", encoding="utf-8")

    monkeypatch.setattr(concurrency_lock, "new_lock_token", lambda: token)
    monkeypatch.setattr(concurrency_lock, "_verify_lock_dir", verify_then_swap)

    lock = acquire_run_lock(root, "workspace")
    try:
        assert calls == 2
        assert (outside / "workspace.lock").read_text(encoding="utf-8") == "outside-token"
        release_run_lock(lock)
        assert (outside / "workspace.lock").read_text(encoding="utf-8") == "outside-token"
        assert not (displaced / "workspace.lock").exists()
    finally:
        _restore_displaced_lock_dir(root / ".canon-locks", displaced)


def test_acquire_registers_capability_after_fake_backend_namespace_swap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    displaced = tmp_path / "displaced-locks"
    root.mkdir()
    outside.mkdir()
    token = "capability-token"
    real_verify = concurrency_lock._verify_lock_dir
    calls = 0
    deleted = False

    def verify_then_swap(lock_dir: Path, snapshot: tuple[Path, int, int]) -> None:
        nonlocal calls
        real_verify(lock_dir, snapshot)
        calls += 1
        if calls == 2:
            _swap_lock_dir_to_symlink(lock_dir, displaced, outside)
            (outside / "workspace.lock").write_text("outside-token", encoding="utf-8")

    def fake_write(lock_dir: Path, lock_name: str, token_arg: str, snapshot: tuple[Path, int, int], verify: object):
        verify(lock_dir, snapshot)
        (lock_dir / lock_name).write_text(token_arg, encoding="utf-8")
        verify(lock_dir, snapshot)
        return concurrency_capability.LockCapability(root, "workspace", lock_name, token_arg, lock_dir / lock_name, "fake", -1, -1, (7,))

    def fake_delete(capability: concurrency_capability.LockCapability) -> None:
        nonlocal deleted
        deleted = True
        (displaced / capability.lock_name).unlink()

    monkeypatch.setattr(concurrency_lock, "new_lock_token", lambda: token)
    monkeypatch.setattr(concurrency_lock, "_can_use_windows_lock", lambda: True)
    monkeypatch.setattr(concurrency_lock, "_verify_lock_dir", verify_then_swap)
    monkeypatch.setattr(concurrency_lock_backend, "write_windows", fake_write)
    monkeypatch.setattr(concurrency_lock_backend, "verify_capability", lambda capability: None)
    monkeypatch.setattr(concurrency_lock_backend, "delete_capability", fake_delete)

    lock = acquire_run_lock(root, "workspace")
    try:
        release_run_lock(lock)
        assert deleted
        assert (outside / "workspace.lock").read_text(encoding="utf-8") == "outside-token"
    finally:
        _restore_displaced_lock_dir(root / ".canon-locks", displaced)


def test_windows_release_uses_same_child_handle_before_close_replacement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lock_dir = tmp_path / ".canon-locks"
    lock_path = lock_dir / "workspace.lock"
    token = "same-handle-token"
    lock_dir.mkdir()
    lock_path.write_text(token, encoding="utf-8")
    lock = RunLock(root=tmp_path, name="workspace", token=token, path=lock_path)
    cap = concurrency_capability.LockCapability(
        tmp_path, "workspace", "workspace.lock", token, lock_path, "windows", 100, 200, (1,)
    )
    calls: list[tuple[object, ...]] = []
    concurrency_lock.register_lock(lock, cap)

    def fake_close(handle: int) -> None:
        calls.append(("close", handle))
        if handle == 200:
            lock_path.write_text("replacement-token", encoding="utf-8")

    def fake_delete_name(dir_ref: int, name: str) -> None:
        calls.append(("delete-name", dir_ref, name))
        lock_path.unlink(missing_ok=True)

    monkeypatch.setattr(concurrency_windows, "file_id", lambda handle: (1,))
    monkeypatch.setattr(concurrency_windows, "read_token", lambda handle: token)
    monkeypatch.setattr(concurrency_windows, "delete_open_file", lambda handle: calls.append(("delete-open", handle)), raising=False)
    monkeypatch.setattr(concurrency_windows, "close_handle", fake_close)
    monkeypatch.setattr(concurrency_windows, "delete_lock_file", fake_delete_name, raising=False)

    release_run_lock(lock)

    assert ("delete-open", 200) in calls
    assert not any(call[0] == "delete-name" for call in calls)
    assert calls.index(("delete-open", 200)) < calls.index(("close", 200))
    assert lock_path.read_text(encoding="utf-8") == "replacement-token"


def test_windows_release_delete_failure_preserves_capability_for_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / ".canon-locks" / "workspace.lock"
    lock_path.parent.mkdir()
    lock = RunLock(root=tmp_path, name="workspace", token="retry-token", path=lock_path)
    owner_id = id(lock)
    lock_ref = weakref.ref(lock)
    cap = concurrency_capability.LockCapability(
        tmp_path, "workspace", "workspace.lock", "retry-token", lock_path, "windows", 10, 20, (2,)
    )
    attempts = 0
    closed: list[int] = []
    concurrency_lock.register_lock(lock, cap)

    def delete_open(handle: int) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError(errno.EACCES, "delete denied")

    monkeypatch.setattr(concurrency_windows, "file_id", lambda handle: (2,))
    monkeypatch.setattr(concurrency_windows, "read_token", lambda handle: "retry-token")
    monkeypatch.setattr(concurrency_windows, "delete_open_file", delete_open, raising=False)
    monkeypatch.setattr(
        concurrency_windows,
        "delete_lock_file",
        lambda dir_ref, name: pytest.fail("must not reopen by name"),
        raising=False,
    )
    monkeypatch.setattr(concurrency_windows, "close_handle", lambda handle: closed.append(handle))

    with pytest.raises(LockError, match="lock-release"):
        release_run_lock(lock)

    assert concurrency_capability.lookup(lock) is cap
    assert (cap.dir_ref, cap.file_ref, cap.released) == (10, 20, False)
    assert closed == []

    release_run_lock(lock)

    assert attempts == 2
    assert cap.released
    assert (cap.dir_ref, cap.file_ref) == (-1, -1)
    assert closed == [20, 10]

    del lock
    _assert_lock_collected(lock_ref, owner_id)


def test_windows_release_native_replacement_after_child_close_survives(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    if os.name != "nt":
        pytest.skip("Windows same-handle delete regression")
    lock = acquire_run_lock(tmp_path, "workspace")
    cap = concurrency_capability.lookup(lock)
    assert cap is not None
    survivor = tmp_path / "survivor.lock"
    real_close = concurrency_windows.close_handle

    def close_then_replace(handle: int) -> None:
        real_close(handle)
        if handle == cap.file_ref:
            try:
                lock.path.rename(survivor)
            except FileNotFoundError:
                pass
            lock.path.write_text("replacement-token", encoding="utf-8")

    monkeypatch.setattr(concurrency_windows, "close_handle", close_then_replace)

    release_run_lock(lock)

    assert lock.path.read_text(encoding="utf-8") == "replacement-token"
    assert not survivor.exists()


def test_release_refuses_lock_path_outside_lock_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside.lock"
    outside.write_text("token", encoding="utf-8")
    lock = RunLock(root=tmp_path, name="workspace", token="token", path=outside)

    with pytest.raises(LockError, match="lock-escape"):
        release_run_lock(lock)
    assert outside.exists()


def test_release_checks_token_ownership_without_deleting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lock = acquire_run_lock(tmp_path, "workspace")
    if os.name == "nt":
        monkeypatch.setattr(concurrency_windows, "read_token", lambda handle: "other-token")
    else:
        lock.path.write_text("other-token", encoding="utf-8")

    with pytest.raises(LockError, match="lock-token-mismatch"):
        release_run_lock(lock)
    assert lock.path.exists()


def test_failed_release_makes_lock_capability_stale(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lock = acquire_run_lock(tmp_path, "workspace")
    if os.name == "nt":
        monkeypatch.setattr(concurrency_windows, "read_token", lambda handle: "other-token")
    else:
        lock.path.write_text("other-token", encoding="utf-8")

    with pytest.raises(LockError, match="lock-token-mismatch"):
        release_run_lock(lock)

    with pytest.raises(LockError, match="lock-stale"):
        release_run_lock(lock)


def test_release_is_idempotent_after_success(tmp_path: Path) -> None:
    lock = acquire_run_lock(tmp_path, "workspace")

    release_run_lock(lock)
    release_run_lock(lock)
    assert not lock.path.exists()


def test_successful_release_does_not_keep_run_lock_alive_after_drop(tmp_path: Path) -> None:
    lock = acquire_run_lock(tmp_path, "workspace")
    owner_id = id(lock)
    lock_ref = weakref.ref(lock)

    release_run_lock(lock)
    release_run_lock(lock)
    assert concurrency_capability.lookup(lock) is not None

    del lock
    _assert_lock_collected(lock_ref, owner_id)


def test_repeated_successful_releases_do_not_accumulate_registry_entries(tmp_path: Path) -> None:
    lock_refs: list[weakref.ReferenceType[RunLock]] = []
    owner_ids: list[int] = []

    for index in range(20):
        lock = acquire_run_lock(tmp_path, f"workspace-{index}")
        owner_ids.append(id(lock))
        lock_refs.append(weakref.ref(lock))
        release_run_lock(lock)
        del lock

    _collect_garbage()

    assert all(lock_ref() is None for lock_ref in lock_refs)
    assert not any(owner_id in concurrency_capability._REGISTRY for owner_id in owner_ids)


def test_stale_released_registry_entry_cannot_authorize_reused_id(tmp_path: Path) -> None:
    stale_owner = _WeakOwner()
    stale_ref = weakref.ref(stale_owner)
    del stale_owner
    _collect_garbage()
    assert stale_ref() is None

    lock_dir = tmp_path / ".canon-locks"
    lock_path = lock_dir / "workspace.lock"
    token = "stale-token"
    lock_dir.mkdir()
    lock_path.write_text(token, encoding="utf-8")
    lock = RunLock(root=tmp_path, name="workspace", token=token, path=lock_path)
    cap = concurrency_capability.LockCapability(
        tmp_path, "workspace", "workspace.lock", token, lock_path, "fake", -1, -1, (9,)
    )
    cap.owner = stale_ref
    cap.released = True
    concurrency_capability._REGISTRY[id(lock)] = cap

    with pytest.raises(LockError, match="lock-stale"):
        release_run_lock(lock)

    assert id(lock) not in concurrency_capability._REGISTRY
    assert lock_path.read_text(encoding="utf-8") == token


def test_release_uses_capability_when_lock_dir_swapped_before_release(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    displaced = tmp_path / "displaced-locks"
    root.mkdir()
    outside.mkdir()
    lock = acquire_run_lock(root, "workspace")
    _swap_lock_dir_to_symlink(root / ".canon-locks", displaced, outside)
    (outside / "workspace.lock").write_text(lock.token, encoding="utf-8")

    try:
        release_run_lock(lock)
        assert (outside / "workspace.lock").read_text(encoding="utf-8") == lock.token
        assert not (displaced / "workspace.lock").exists()
    finally:
        _restore_displaced_lock_dir(root / ".canon-locks", displaced)


def test_release_does_not_delete_outside_after_validation_race(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    displaced = tmp_path / "displaced-locks"
    root.mkdir()
    outside.mkdir()
    lock = acquire_run_lock(root, "workspace")
    (outside / "workspace.lock").write_text(lock.token, encoding="utf-8")
    real_assert = concurrency_lock._assert_release_target

    def assert_then_swap(root_path: Path, name: str, lock_path: Path) -> None:
        real_assert(root_path, name, lock_path)
        _swap_lock_dir_to_symlink(root_path / ".canon-locks", displaced, outside)

    monkeypatch.setattr(concurrency_lock, "_assert_release_target", assert_then_swap)

    try:
        release_run_lock(lock)
        assert (outside / "workspace.lock").read_text(encoding="utf-8") == lock.token
        assert not (displaced / "workspace.lock").exists()
    finally:
        _restore_displaced_lock_dir(root / ".canon-locks", displaced)


def test_release_registered_capability_survives_fake_validation_swap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    displaced = tmp_path / "displaced-locks"
    lock_dir = root / ".canon-locks"
    lock_path = lock_dir / "workspace.lock"
    token = "registered-token"
    lock_dir.mkdir(parents=True)
    outside.mkdir()
    lock_path.write_text(token, encoding="utf-8")
    lock = RunLock(root=root, name="workspace", token=token, path=lock_path)
    cap = concurrency_capability.LockCapability(root, "workspace", "workspace.lock", token, lock_path, "fake", -1, -1, (3,))
    concurrency_lock.register_lock(lock, cap)
    real_assert = concurrency_lock._assert_release_target

    def assert_then_swap(root_path: Path, name: str, path: Path) -> None:
        real_assert(root_path, name, path)
        _swap_lock_dir_to_symlink(root_path / ".canon-locks", displaced, outside)
        (outside / "workspace.lock").write_text(token, encoding="utf-8")

    def fake_delete(capability: concurrency_capability.LockCapability) -> None:
        (displaced / capability.lock_name).unlink()

    monkeypatch.setattr(concurrency_lock, "_assert_release_target", assert_then_swap)
    monkeypatch.setattr(concurrency_lock_backend, "verify_capability", lambda capability: None)
    monkeypatch.setattr(concurrency_lock_backend, "delete_capability", fake_delete)

    try:
        release_run_lock(lock)
        assert (outside / "workspace.lock").read_text(encoding="utf-8") == token
        assert not (displaced / "workspace.lock").exists()
    finally:
        _restore_displaced_lock_dir(root / ".canon-locks", displaced)


def test_release_swap_back_cannot_authorize_with_outside_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    displaced = tmp_path / "displaced-locks"
    root.mkdir()
    outside.mkdir()
    lock = acquire_run_lock(root, "workspace")
    if os.name == "nt":
        monkeypatch.setattr(concurrency_windows, "read_token", lambda handle: "tampered-token")
    else:
        lock.path.write_text("tampered-token", encoding="utf-8")
    (outside / "workspace.lock").write_text(lock.token, encoding="utf-8")
    real_verify = concurrency_lock_backend.verify_capability
    swapped = False

    def verify_through_swap_back(capability: object) -> None:
        nonlocal swapped
        if not swapped:
            swapped = True
            _swap_lock_dir_to_symlink(root / ".canon-locks", displaced, outside)
            try:
                real_verify(capability)
            finally:
                _restore_displaced_lock_dir(root / ".canon-locks", displaced)
        else:
            real_verify(capability)

    monkeypatch.setattr(concurrency_lock_backend, "verify_capability", verify_through_swap_back)

    with pytest.raises(LockError, match="lock-token-mismatch"):
        release_run_lock(lock)

    assert lock.path.exists()
    assert (outside / "workspace.lock").exists()


def test_release_rejects_forged_run_lock_without_deleting_matching_file(tmp_path: Path) -> None:
    lock_dir = tmp_path / ".canon-locks"
    lock_path = lock_dir / "workspace.lock"
    lock_dir.mkdir()
    lock_path.write_text("forged-token", encoding="utf-8")
    forged = RunLock(root=tmp_path, name="workspace", token="forged-token", path=lock_path)

    with pytest.raises(LockError, match="lock-stale"):
        release_run_lock(forged)

    assert lock_path.read_text(encoding="utf-8") == "forged-token"


def test_release_rejects_copied_run_lock_without_releasing_real_lock(tmp_path: Path) -> None:
    real = acquire_run_lock(tmp_path, "workspace")
    copied = RunLock(root=real.root, name=real.name, token=real.token, path=real.path)

    with pytest.raises(LockError, match="lock-stale"):
        release_run_lock(copied)

    assert real.path.exists()
    release_run_lock(real)
    assert not real.path.exists()


def test_release_rejects_reparse_lock_file(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    lock_dir = root / ".canon-locks"
    lock_dir.mkdir()
    target = tmp_path / "outside.lock"
    target.write_text("token", encoding="utf-8")
    link = lock_dir / "workspace.lock"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("current platform or privileges do not allow file symlinks")
    lock = RunLock(root=root, name="workspace", token="token", path=link)

    with pytest.raises(LockError, match="lock-stale"):
        release_run_lock(lock)
    assert link.exists() or link.is_symlink()
    assert target.exists()


def test_release_rejects_directory_lock_path_before_reading(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    lock_dir = root / ".canon-locks"
    lock_path = lock_dir / "workspace.lock"
    lock_path.mkdir(parents=True)
    lock = RunLock(root=root, name="workspace", token="token", path=lock_path)

    def fail_read_text(self: Path, *args: object, **kwargs: object) -> str:
        raise AssertionError("non-regular lock path must be rejected before read")

    monkeypatch.setattr(Path, "read_text", fail_read_text)

    with pytest.raises(LockError, match="lock-stale"):
        release_run_lock(lock)

    assert lock_path.is_dir()


def test_release_rejects_special_lock_path_before_reading(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    if not hasattr(socket, "AF_UNIX"):
        pytest.skip("platform has no safe non-blocking socket path support")
    root = tmp_path / "root"
    lock_dir = root / ".canon-locks"
    lock_dir.mkdir(parents=True)
    lock_path = lock_dir / "workspace.lock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        try:
            server.bind(str(lock_path))
        except OSError:
            pytest.skip("platform cannot create a safe socket lock path")
        lock = RunLock(root=root, name="workspace", token="token", path=lock_path)

        def fail_read_text(self: Path, *args: object, **kwargs: object) -> str:
            raise AssertionError("non-regular lock path must be rejected before read")

        monkeypatch.setattr(Path, "read_text", fail_read_text)

        with pytest.raises(LockError, match="lock-stale"):
            release_run_lock(lock)
    finally:
        server.close()


def test_acquire_cleans_up_partial_lock_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = 0

    def partial_then_fail(fd: int, data: bytes) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            return max(1, len(data) // 2)
        raise OSError(errno.ENOSPC, "no space left")

    def fail_windows_write(handle: int, data: bytes) -> None:
        raise OSError(errno.ENOSPC, "no space left")

    if os.name == "nt":
        monkeypatch.setattr(concurrency_windows, "_write_file", fail_windows_write)
    else:
        monkeypatch.setattr(os, "write", partial_then_fail)

    with pytest.raises(LockError, match="lock-write") as caught:
        acquire_run_lock(tmp_path, "workspace")

    assert isinstance(caught.value.__cause__, OSError)
    assert not (tmp_path / ".canon-locks" / "workspace.lock").exists()


def test_acquire_maps_raw_stable_open_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def deny_open(*args: object, **kwargs: object) -> int:
        raise PermissionError(errno.EACCES, "denied")

    def deny_windows_open(path: Path) -> int:
        raise PermissionError(errno.EACCES, "denied")

    if os.name == "nt":
        monkeypatch.setattr(concurrency_windows, "open_directory", deny_windows_open)
    else:
        monkeypatch.setattr(os, "open", deny_open)

    with pytest.raises(LockError, match="lock-open") as caught:
        acquire_run_lock(tmp_path, "workspace")

    assert isinstance(caught.value.__cause__, PermissionError)


def test_guarded_commit_aborts_without_calling_commit_on_source_change() -> None:
    item = SourceStateItem(path="a.md", sha256=_sha("a"), size=1)
    called = False

    def commit() -> str:
        nonlocal called
        called = True
        return "written"

    with pytest.raises(SourceStateError):
        guarded_commit(_sha("f"), (item,), commit)

    assert not called
    assert guarded_commit(source_state_sha256((item,)), (item,), commit) == "written"


def test_guarded_commit_aborts_without_calling_commit_on_invalid_state() -> None:
    called = False

    def commit() -> str:
        nonlocal called
        called = True
        return "written"

    with pytest.raises(SourceStateError, match="invalid-source-state"):
        guarded_commit("not-a-digest", (), commit)

    assert not called


def test_guarded_commit_aborts_without_calling_commit_on_mutated_source_item() -> None:
    item = SourceStateItem(path="a.md", sha256=_sha("a"), size=1)
    expected = source_state_sha256((item,))
    object.__setattr__(item, "size", True)
    called = False

    def commit() -> str:
        nonlocal called
        called = True
        return "written"

    with pytest.raises(SourceStateError, match="invalid-source-state-item"):
        guarded_commit(expected, (item,), commit)

    assert not called


def test_guarded_commit_rejects_hostile_item_subclass_without_calling_commit() -> None:
    called = False

    def commit() -> str:
        nonlocal called
        called = True
        return "written"

    with pytest.raises(SourceStateError, match="invalid-source-state"):
        guarded_commit(_hostile_source_digest(), (_hostile_source_item(),), commit)

    assert not called


def test_guarded_commit_rejects_hostile_tuple_subclass_without_calling_commit() -> None:
    called = False

    def commit() -> str:
        nonlocal called
        called = True
        return "written"

    with pytest.raises(SourceStateError, match="invalid-source-state"):
        guarded_commit(_hostile_source_digest(), _hostile_source_tuple(), commit)

    assert not called


def test_guarded_commit_requires_callable_after_state_validation() -> None:
    item = SourceStateItem(path="a.md", sha256=_sha("a"), size=1)

    with pytest.raises(LockError, match="invalid-commit"):
        guarded_commit(source_state_sha256((item,)), (item,), object())
