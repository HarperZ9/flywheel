"""win_wait.py -- wait on a Windows process handle with a timeout and a cancel flag.

WaitForSingleObject waits in one call and cannot be interrupted, so a caller
that must stop a long-running command (a background job the user stopped)
waits in short slices and checks the flag between them.
"""
from __future__ import annotations

import time

CANCELLED = -2
SLICE_MS = 250


def wait_until(kernel, handle, timeout_seconds: int, cancel=None, *,
               wait_timeout: int = 0x102) -> int:
    """WaitForSingleObject's result, its WAIT_TIMEOUT at the deadline, or CANCELLED."""
    if cancel is None:
        return kernel.WaitForSingleObject(handle, timeout_seconds * 1000)
    deadline = time.monotonic() + timeout_seconds
    while True:
        if cancel.is_set():
            return CANCELLED
        left = int((deadline - time.monotonic()) * 1000)
        if left <= 0:
            return wait_timeout
        waited = kernel.WaitForSingleObject(handle, min(SLICE_MS, left))
        if waited != wait_timeout:
            return waited
