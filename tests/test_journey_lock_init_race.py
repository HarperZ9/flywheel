"""A caller that finds an empty lock file must not fail when a racing holder locks it first."""
import os

import pytest

import harness.journey_lock as locks
from harness.journey_lock import ExclusiveJourneyLock, JourneyLockBusy


def _hold_first_byte(path):
    """Lock byte 0 of an empty lock file from another handle, as a racing holder does."""
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+b", buffering=0)
    assert locks._try_lock(stream)
    return stream


def test_empty_lock_file_held_by_another_handle_is_busy_not_an_error(tmp_path):
    # On Windows the runtime's append mode seeks to the end and writes in two
    # steps, and byte-range locks are enforced on writes. A caller that saw an
    # empty file can therefore aim its initial byte at offset 0 after another
    # caller has already locked that byte. The lock is held, so the caller must
    # see STORE_BUSY, never an unclassified PermissionError.
    path = tmp_path / "locks" / "k.lock"
    holder = _hold_first_byte(path)
    try:
        assert path.stat().st_size == 0
        with pytest.raises(JourneyLockBusy):
            with ExclusiveJourneyLock.acquire(path, 0.0):
                pytest.fail("acquired a lock another handle holds")
    finally:
        locks._unlock(holder)
        holder.close()


def test_the_caller_takes_the_lock_once_the_racing_holder_releases(tmp_path):
    path = tmp_path / "locks" / "k.lock"
    holder = _hold_first_byte(path)
    locks._unlock(holder)
    holder.close()
    with ExclusiveJourneyLock.acquire(path, 0.0):
        assert path.stat().st_size == 1


@pytest.mark.skipif(os.name != "nt", reason="Windows byte-range locks only")
def test_a_write_failure_without_a_holder_still_raises(tmp_path, monkeypatch):
    # The tolerance covers a held lock only. If the byte is free, the write
    # failure is a real error and must surface.
    path = tmp_path / "locks" / "k.lock"
    path.parent.mkdir(parents=True)

    class RefusingStream:
        def __init__(self, inner):
            self._inner = inner

        def write(self, data):
            raise PermissionError(13, "Permission denied")

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._inner.close()

    real_open = type(path).open
    monkeypatch.setattr(type(path), "open",
                        lambda self, *a, **k: RefusingStream(real_open(self, *a, **k)))
    with pytest.raises(PermissionError):
        with ExclusiveJourneyLock.acquire(path, 0.0):
            pass
