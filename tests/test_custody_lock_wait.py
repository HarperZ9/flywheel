"""A long deletion does not make new captures fail. The deletion holds the
custody lock for its steps only; its verification (the residual scan, which
grows with the run root) runs without it. A new item key waits past the
usual lock timeout for a busy custody writer and says that it waits."""
import logging
import threading

import pytest

from delete_fixtures import OWNER, plant_trace
from harness import trace_keystore
from harness.trace_custody_lock import custody_lock, is_held
from harness.trace_delete_plan import make_plan
from harness.trace_keystore import Keystore
from trace_enc_fakes import StreamTestProvider, using


@pytest.fixture
def home(tmp_path):
    with using(StreamTestProvider()):
        (tmp_path / "state").mkdir()
        yield tmp_path


def test_a_new_key_waits_for_a_busy_writer_and_says_so(home, monkeypatch, caplog):
    monkeypatch.setattr(trace_keystore, "FIRST_WAIT_S", 0.3)
    monkeypatch.setattr(trace_keystore, "KEY_WAIT_S", 10.0)
    taken, release = threading.Event(), threading.Event()

    def holder():
        with custody_lock(home / "state"):
            taken.set()
            release.wait(5)
    thread = threading.Thread(target=holder)
    thread.start()
    taken.wait(5)
    threading.Timer(1.0, release.set).start()
    with caplog.at_level(logging.WARNING, logger="harness.trace_keystore"):
        key = Keystore(home / "state", OWNER).item_key("S1", "agt_" + "e" * 32, create=True)
    thread.join()
    assert key is not None and len(key) == 32
    assert any("waiting" in r.getMessage() for r in caplog.records)


def test_verification_runs_without_the_custody_lock(home, monkeypatch):
    from harness import trace_delete_apply
    from harness.trace_delete_apply import apply_plan
    from harness.trace_presence import confirm
    from harness.trace_witness import MemorySink
    held = []
    real = trace_delete_apply._verifier

    def spy(*a, **k):
        verify = real(*a, **k)
        return lambda scan_set: held.append(is_held(home / "state")) or verify(scan_set)
    monkeypatch.setattr(trace_delete_apply, "_verifier", spy)
    plan = make_plan(home, OWNER, {"trace_refs": [plant_trace(home)]})
    token = confirm(home / "state", OWNER, "delete_apply", plan["plan_digest"], "delete")
    report = apply_plan(home, OWNER, plan["plan_digest"], token, sink=MemorySink())
    assert report["state"] == "DELETED" and held == [False]
