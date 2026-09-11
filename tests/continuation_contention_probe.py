"""Test-only outer-lock clock and bounded continuation watchdog evidence."""
from collections import deque
from concurrent.futures import wait
from contextlib import contextmanager, ExitStack
import json
from pathlib import Path
import sys
import threading
import time


class AcquisitionClock:
    def __init__(self):
        self.local = threading.local()

    @contextmanager
    def caller(self):
        self.local.value = 0.0
        try:
            yield
        finally:
            del self.local.value

    def monotonic(self):
        return self.local.value if hasattr(self.local, "value") else time.monotonic()

    def expire(self):
        assert hasattr(self.local, "value")
        self.local.value = 3.0

    @contextmanager
    def acquire(self, real_acquire, path, timeout_s=2.0, *, outer_path):
        with ExitStack() as stack:
            if Path(path) == outer_path:
                with self.caller():
                    stack.enter_context(real_acquire(path, timeout_s))
            else:
                stack.enter_context(real_acquire(path, timeout_s))
            # Only the outer acquisition is controlled. Held work and every
            # nested grant/Journey acquisition retain their real deadline.
            yield


class ContentionProbe:
    def __init__(self):
        self.started = time.monotonic()
        self.guard = threading.Lock()
        self.events = deque(maxlen=80)
        self.threads = {}

    def record(self, phase, **fields):
        thread = threading.get_ident()
        event = {"elapsed_s": round(time.monotonic() - self.started, 6),
                 "thread": thread, "phase": phase, **fields}
        with self.guard:
            self.events.append(event)
            self.threads[thread] = {**self.threads.get(thread, {}), **event}

    def diagnostic(self, futures):
        frames = sys._current_frames()
        with self.guard:
            events = list(self.events)
            threads = [dict(value) for value in self.threads.values()]
        for thread in threads:
            frame = frames.get(thread["thread"])
            stack = []
            while frame is not None:
                stack.append(f"{Path(frame.f_code.co_filename).name}:"
                             f"{frame.f_lineno}:{frame.f_code.co_name}")
                frame = frame.f_back
            thread["stack"] = stack
        return json.dumps({"completed": sum(future.done() for future in futures),
                           "total": len(futures), "events": events,
                           "threads": threads}, sort_keys=True)


def collect_results(futures, *, timeout, probe):
    results = []
    for future in futures:
        completed, _ = wait([future], timeout=timeout)
        if not completed:
            message = "continuation contention timed out: " + probe.diagnostic(futures)
            # Emit before the executor's shutdown(wait=True) can stall teardown.
            print(message, file=sys.stderr, flush=True)
            raise AssertionError(message)
        results.append(future.result())
    return results
