"""Local cancellation orders credential commit; it does not revoke a provider token."""
import threading


class SigninAttempt:
    def __init__(self):
        self.cancelled = threading.Event()
        self._lock = threading.Lock()
        self._finished = False

    def cancel(self):
        with self._lock:
            if self._finished:
                return False
            self.cancelled.set()
            return True

    def commit(self, action, cancelled_result):
        # Never acquire the service lock here. Service operations may hold it
        # while cancelling this attempt, before deleting a local credential.
        with self._lock:
            if self.cancelled.is_set():
                return cancelled_result
            try:
                return action()
            finally:
                self._finished = True

    def finish(self):
        with self._lock:
            self._finished = True
