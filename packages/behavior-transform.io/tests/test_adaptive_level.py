import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from provider_intelligence import IntelStore, IntelEvent
from inference_loop import InferenceLoop


def _make_responder(responses):
    idx = [0]
    def send_fn(system, messages):
        i = min(idx[0], len(responses) - 1)
        idx[0] += 1
        return responses[i]
    return send_fn


def _seed_store(store, provider, successes_at_level):
    """Seed the store with events showing success at a specific level."""
    import time
    for level, count in successes_at_level.items():
        for _ in range(count):
            store.record_interaction(
                provider=provider,
                modulation_level=level,
                outcome="success",
                quality_score=0.9,
            )
    # Add some failures at level 0 to make the optimizer avoid it
    for _ in range(5):
        store.record_interaction(
            provider=provider,
            modulation_level=0,
            outcome="hard_refusal",
            quality_score=0.1,
        )


def test_starts_at_optimal_level_from_history():
    with tempfile.TemporaryDirectory() as tmp:
        store = IntelStore(Path(tmp))
        _seed_store(store, "anthropic", {0: 2, 2: 8, 3: 3})

        profile = store.profile("anthropic")
        assert profile.optimal_level == 2

        send = _make_responder(["The answer is correct."])
        loop = InferenceLoop(
            send, record_intel=True, adaptive_start=True,
        )
        loop._intel_store = store
        loop._provider = "anthropic"
        result = loop.run("Question.", [])
        assert result.succeeded is True
        assert result.attempts[0].level == 2


def test_falls_back_to_zero_without_history():
    with tempfile.TemporaryDirectory() as tmp:
        store = IntelStore(Path(tmp))
        send = _make_responder(["The answer is correct."])
        loop = InferenceLoop(
            send, record_intel=True, adaptive_start=True,
        )
        loop._intel_store = store
        loop._provider = "anthropic"
        result = loop.run("Question.", [])
        assert result.succeeded is True
        assert result.attempts[0].level == 0


def test_still_escalates_from_adaptive_start():
    with tempfile.TemporaryDirectory() as tmp:
        store = IntelStore(Path(tmp))
        _seed_store(store, "anthropic", {2: 10})

        send = _make_responder([
            "I cannot and will not help with that.",
            "I cannot and will not help with that.",
            "Here is the real answer.",
        ])
        loop = InferenceLoop(
            send, record_intel=True, adaptive_start=True,
        )
        loop._intel_store = store
        loop._provider = "anthropic"
        result = loop.run("Question.", [])
        assert result.succeeded is True
        assert result.attempts[0].level == 2
        assert result.final_level > 2
