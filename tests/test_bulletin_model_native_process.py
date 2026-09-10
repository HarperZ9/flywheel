"""Decoded native process diagnostics through fake owned processes only."""
from types import SimpleNamespace
from threading import Event, Thread
import hashlib
import json
import pytest

from harness.bulletin_model_native_process import NativeProcessCapture, ProcessCaptureError, close_from_watchdog, record_start_failure
from harness.bulletin_model_exchange import ExchangeError
from harness.bulletin_model_native import NativeCoordinator


class Store:
    def __init__(self):
        self.records = {}; self.fail = None

    def put(self, name, raw, *, max_bytes):
        if name == self.fail or name in self.records or len(raw) > max_bytes:
            raise ExchangeError("record_write_failed")
        self.records[name] = raw
        return hashlib.sha256(raw).hexdigest()


class Owner:
    def __init__(self, outcome):
        self.outcome = outcome; self.terminal = False; self.closed = False; self.waits = 0

    def resume(self):
        return True

    def wait(self, timeout):
        self.waits += 1
        return self.outcome if self.terminal or self.closed else None

    def close(self):
        self.closed = True


def outcome(**changes):
    return SimpleNamespace(**{**dict(returncode=1, stdout="decoded stdout Ω", stderr="Flutter launch failed",
                                    elapsed_ms=97, timed_out=False, malformed_output=False), **changes})


def capture(owner, store):
    return NativeProcessCapture(owner, store, {"schema_version": 1, "run_id": "run", "slot_id": "s01"})


def test_terminal_capture_is_durable_and_labeled_decoded_not_raw():
    o, store = Owner(outcome()), Store(); o.terminal = True; child = capture(o, store)
    assert child.resume()
    assert child.wait(0) is o.outcome
    receipt = json.loads(store.records["native-process.json"])
    assert receipt["capture_kind"] == "decoded_process_outcome_not_raw_bytes"
    assert receipt["observed_during"] == "terminal_wait" and receipt["returncode"] == 1
    assert receipt["elapsed_ms"] == 97 and receipt["malformed_output"] is False
    assert store.records["native-stdout.txt"].decode() == "decoded stdout Ω"
    assert receipt["outputs"]["stderr"]["sha256"] == hashlib.sha256(store.records["native-stderr.txt"]).hexdigest()
    child.close(); child.close(); assert child.wait(0) is o.outcome
    assert len(store.records) == 3 and o.closed


def test_cleanup_collects_output_after_owned_shutdown():
    o, store = Owner(outcome(returncode=-1, timed_out=True)), Store(); child = capture(o, store)
    assert child.wait(0) is None and not store.records
    child.close()
    receipt = json.loads(store.records["native-process.json"])
    assert o.closed and receipt["observed_during"] == "owned_cleanup" and receipt["timed_out"] is True


def test_decoded_truncation_is_bounded_and_upstream_malformed_flag_is_preserved():
    o, store = Owner(outcome(stdout="☃" * 400000, stderr="", malformed_output=True)), Store()
    child = capture(o, store); child.close()
    receipt = json.loads(store.records["native-process.json"])
    assert len(store.records["native-stdout.txt"]) <= 1048576
    store.records["native-stdout.txt"].decode("utf-8", "strict")
    assert receipt["outputs"]["stdout"]["truncated"] is True
    assert receipt["malformed_output"] is True
    assert receipt["outputs"]["stdout"]["available_decoded_utf8_bytes"] == 1200000


def test_missing_cleanup_outcome_keeps_capture_unknown_not_empty():
    o, store = Owner(None), Store(); child = capture(o, store); child.close()
    receipt = json.loads(store.records["native-process.json"])
    assert receipt["capture_available"] is False and receipt["returncode"] is None
    assert receipt["outputs"] is None
    assert set(store.records) == {"native-process.json"}


def test_failed_capture_latches_and_still_terminates_owned_process():
    o, store = Owner(outcome()), Store(); o.terminal = True; store.fail = "native-process.json"
    child = capture(o, store)
    with pytest.raises(ProcessCaptureError): child.wait(0)
    assert child.failed
    with pytest.raises(ProcessCaptureError): child.close()
    assert o.closed
    assert "native-process.json" not in store.records


def test_watchdog_recording_failure_is_latched_without_thread_traceback():
    class Coordinator:
        failed = False
        def close(self): raise ProcessCaptureError("recording_failed")
    value = Coordinator(); close_from_watchdog(value)
    assert value.failed


def test_repeated_coordinator_close_waits_for_watchdog_capture_before_store_teardown():
    entered, release, second_entered, second_done = Event(), Event(), Event(), Event()
    class BlockingStore(Store):
        def put(self, name, raw, **kwargs):
            entered.set()
            assert release.wait(2), "test must release capture"
            return super().put(name, raw, **kwargs)
    store = BlockingStore()
    coordinator = SimpleNamespace(watchdog=None, closed=False, process=capture(Owner(outcome()), store))
    def close_again():
        second_entered.set(); NativeCoordinator.close(coordinator); second_done.set()
    first = Thread(target=lambda: NativeCoordinator.close(coordinator), daemon=True)
    second = Thread(target=close_again, daemon=True)
    first.start(); assert entered.wait(1)
    try:
        second.start(); assert second_entered.wait(1)
        assert not second_done.wait(0.05), "close returned while receipt writer still held the store"
    finally:
        release.set(); first.join(2); second.join(2)
    assert second_done.is_set() and "native-process.json" in store.records


def test_start_failure_keeps_original_separate_from_cleanup_without_secret_exception_text():
    class Coordinator:
        failed = False
        exchange = Store()
        def _base(self): return {"schema_version": 1, "run_id": "run", "slot_id": "s01"}
        def close(self): raise ProcessCaptureError("PRIVATE cleanup details")
    c = Coordinator()
    original = OSError(5, "PRIVATE startup payload")
    record_start_failure(c, original)
    receipt = json.loads(c.exchange.records["native-startup-failure.json"])
    assert receipt["startup"][0]["type"] == "OSError" and receipt["startup"][0]["errno"] == 5
    assert receipt["cleanup"][0]["type"] == "ProcessCaptureError" and c.failed
    assert "PRIVATE" not in json.dumps(receipt)


def test_start_failure_remains_available_in_memory_if_receipt_sink_is_unusable():
    store = Store(); store.fail = "native-startup-failure.json"
    c = SimpleNamespace(exchange=store, _base=lambda: {"schema_version": 1}, close=lambda: None, failed=False)
    record_start_failure(c, ValueError("private original"))
    assert c.failed and c.startup_failure["startup"][0]["type"] == "ValueError"
    assert "native-startup-failure.json" not in store.records
