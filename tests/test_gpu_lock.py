"""The GPU directory lock: atomic acquire, and release only by its owner."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import gpu_lock  # noqa: E402


def test_acquire_writes_owner_and_a_second_acquire_is_refused(tmp_path):
    lock = tmp_path / "gpu.lock.d"
    token = gpu_lock.acquire(lock, "test")
    assert gpu_lock.owner(lock)["token"] == token
    with pytest.raises(gpu_lock.LockError):
        gpu_lock.acquire(lock, "someone else")


def test_release_needs_the_owners_token(tmp_path):
    lock = tmp_path / "gpu.lock.d"
    token = gpu_lock.acquire(lock, "test")
    with pytest.raises(gpu_lock.LockError):
        gpu_lock.release(lock, "not-the-token")
    assert lock.exists()
    gpu_lock.release(lock, token)
    assert not lock.exists()


def test_a_lock_held_by_another_tool_without_a_token_is_never_released(tmp_path):
    lock = tmp_path / "gpu.lock.d"
    lock.mkdir()
    (lock / "OWNER").write_text('{"pid": 1, "purpose": "other"}', encoding="utf-8")
    with pytest.raises(gpu_lock.LockError):
        gpu_lock.release(lock, "")
    assert (lock / "OWNER").exists()
