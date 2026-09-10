"""Private native-driver diagnostics around the existing owned-process API.

ProcessOutcome exposes decoded text, possibly already truncated or discarded
by its reader. Re-encoding it cannot recover raw bytes or per-stream loss.
"""
from __future__ import annotations

from threading import RLock

from .cross_harness_process import MAX_CAPTURE_BYTES
from .evidence_json import canonical_bytes


class ProcessCaptureError(RuntimeError):
    """Fixed diagnostic; captured output is never part of the exception."""


class NativeProcessCapture:
    def __init__(self, owner, store, binding, *, on_failure=None):
        self.owner, self.store, self.binding = owner, store, dict(binding)
        self.on_failure = on_failure
        self.failed = self._recorded = self._closed = False
        self._outcome = None
        self._lock = RLock()

    def _fail(self):
        self.failed = True
        if self.on_failure is not None:
            self.on_failure()
        raise ProcessCaptureError("native_process_capture_failed") from None

    def resume(self):
        return self.owner.resume()

    def stdout_snapshot(self):
        return self.owner.stdout_snapshot()  # Existing API remains distinct from decoded receipts.

    def wait(self, timeout_s):
        with self._lock:
            if self.failed:
                self._fail()
            if self._outcome is None:
                self._outcome = self.owner.wait(timeout_s)
            if self._outcome is not None:
                self._record("terminal_wait")
            return self._outcome

    def close(self):
        with self._lock:
            if self._closed:
                return  # Lock acquisition joins any earlier cleanup/capture first.
            self._closed = True
            try:
                self.owner.close()
                if self._outcome is None:
                    self._outcome = self.owner.wait(0.5)
            except Exception:
                self._fail()
            if self.failed:
                self._fail()
            self._record("owned_cleanup")

    def _record(self, observed_during):
        if self._recorded:
            return
        try:
            outcome = self._outcome
            metadata = {key: getattr(outcome, key) if outcome is not None else None
                        for key in ("returncode", "elapsed_ms", "timed_out", "malformed_output")}
            outputs = None
            if outcome is not None:
                if (any(type(metadata[k]) is not int for k in ("returncode", "elapsed_ms"))
                        or metadata["elapsed_ms"] < 0
                        or any(type(metadata[k]) is not bool for k in ("timed_out", "malformed_output"))):
                    raise ValueError("invalid_process_outcome")
                outputs = {}
                for stream in ("stdout", "stderr"):
                    text = getattr(outcome, stream)
                    if type(text) is not str:
                        raise ValueError("invalid_decoded_output")
                    raw = text.encode("utf-8", "strict")
                    kept = raw[:MAX_CAPTURE_BYTES].decode("utf-8", "ignore").encode("utf-8")
                    name = f"native-{stream}.txt"
                    outputs[stream] = {"record_name": name, "sha256": self.store.put(
                        name, kept, max_bytes=MAX_CAPTURE_BYTES), "truncated": len(kept) < len(raw),
                        "stored_bytes": len(kept), "available_decoded_utf8_bytes": len(raw)}
            self.store.put("native-process.json", canonical_bytes({**self.binding,
                "capture_kind": "decoded_process_outcome_not_raw_bytes", "capture_available": outcome is not None,
                "observed_during": observed_during, **metadata, "outputs": outputs,
                "limit": "Decoded ProcessOutcome text only; upstream malformed_output may reflect loss or overflow. Raw bytes and per-stream upstream loss are unavailable."}), max_bytes=8192)
            self._recorded = True
        except Exception:
            self._fail()


def close_from_watchdog(coordinator):
    """A watchdog cannot raise into its caller; latch failures without a traceback."""
    try:
        coordinator.close()
    except Exception:
        coordinator.failed = True


def _failure_chain(error):
    """Keep failure categories, never arbitrary messages, paths or arguments."""
    classes = {"NativeError", "NativeRecordingError", "ProcessCaptureError", "ExchangeError",
               "PrivateArtifactError", "OSError", "PermissionError", "FileNotFoundError", "ValueError", "TypeError"}
    codes = {"NOT_FOUND", "UNSAFE_PATH", "NOT_REGULAR", "TOO_LARGE", "CONFLICT", "IO_ERROR", "BUSY", "CLOSED",
             "UNSUPPORTED_OS", "UNSUPPORTED_FS", "native_invalid", "native_timeout", "native_driver_exited",
             "record_write_failed", "record_read_failed", "native_recording_failed", "native_process_capture_failed"}
    chain, seen = [], set()
    while error is not None and id(error) not in seen and len(chain) < 8:
        seen.add(id(error))
        code = getattr(error, "code", None)
        if code is None and error.args:
            code = error.args[0]
        kind = type(error).__name__
        chain.append({"type": kind if kind in classes else "other_exception",
                      "code": code if type(code) is str and code in codes else None,
                      "errno": getattr(error, "errno", None) if type(getattr(error, "errno", None)) is int else None,
                      "winerror": getattr(error, "winerror", None) if type(getattr(error, "winerror", None)) is int else None})
        error = error.__cause__ or error.__context__
    return chain


def record_start_failure(coordinator, error):
    """A cleanup failure must not erase the already observed startup failure."""
    record = {**coordinator._base(), "startup": _failure_chain(error), "cleanup": None}
    coordinator.startup_failure = record
    try:
        coordinator.close()
    except Exception as cleanup:
        coordinator.failed = True
        record["cleanup"] = _failure_chain(cleanup)
    try:
        coordinator.exchange.put("native-startup-failure.json", canonical_bytes(record), max_bytes=8192)
    except Exception:
        coordinator.failed = True  # In-memory categories survive even when the sink is broken.
