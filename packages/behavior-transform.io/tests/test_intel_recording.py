import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from inference_loop import InferenceLoop
from provider_intelligence import IntelStore


def _make_responder(responses):
    idx = [0]
    def send_fn(system, messages):
        i = min(idx[0], len(responses) - 1)
        idx[0] += 1
        return responses[i]
    return send_fn


def test_records_success():
    with tempfile.TemporaryDirectory() as tmp:
        store = IntelStore(Path(tmp))
        send = _make_responder(["The answer is 42."])
        loop = InferenceLoop(send, record_intel=True)
        loop._intel_store = store
        loop.run("What is the answer?", [])
        events = store.load_events()
        assert len(events) == 1
        assert events[0].outcome == "success"
        assert events[0].modulation_level == 0


def test_records_escalation():
    with tempfile.TemporaryDirectory() as tmp:
        store = IntelStore(Path(tmp))
        send = _make_responder([
            "I cannot and will not help.",
            "I cannot and will not help.",
            "Here is the answer.",
        ])
        loop = InferenceLoop(send, record_intel=True)
        loop._intel_store = store
        loop.run("Question.", [])
        events = store.load_events()
        assert len(events) == 3
        assert events[0].outcome in ("hard_refusal", "soft_refusal")
        assert events[2].outcome == "success"
        assert events[2].modulation_level == 2


def test_records_exhaustion():
    with tempfile.TemporaryDirectory() as tmp:
        store = IntelStore(Path(tmp))
        send = _make_responder([
            "I cannot and will not help with that.",
        ] * 6)
        loop = InferenceLoop(send, record_intel=True)
        loop._intel_store = store
        loop.run("Question.", [])
        events = store.load_events()
        assert len(events) == 6
        assert all(e.outcome != "success" for e in events)
