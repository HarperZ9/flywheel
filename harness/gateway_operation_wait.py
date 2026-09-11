"""Bounded polling of an existing operation through transient store contention."""
from __future__ import annotations

import time

from .gateway_operation import GatewayOperationError


def wait_for_terminal(read_snapshot, terminal_states, condition, timeout_s,
                      *, clock=None):
    """Retry only busy reads without resetting the caller's wait deadline.

    Each read retains its existing store-acquisition bound. The event condition
    wakes polling promptly when a lifecycle event commits, as in the SSE reader.
    """
    if clock is None:
        clock = time.monotonic
    deadline = clock() + timeout_s
    busy = False
    while clock() < deadline:
        try:
            snapshot = read_snapshot()
        except GatewayOperationError as exc:
            if exc.code != "STORE_BUSY":
                raise
            busy = True
        else:
            busy = False
            if snapshot.state in terminal_states:
                return snapshot
        remaining = max(0, deadline - clock())
        if remaining:
            with condition:
                condition.wait(min(.05, remaining))
    if busy:
        raise GatewayOperationError("STORE_BUSY") from None
    raise TimeoutError("gateway operation did not become terminal")
