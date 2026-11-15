import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from inference_loop import InferenceLoop, LoopResult


def _make_responder(responses: list[str]):
    """Return a send_fn that yields responses in order."""
    call_count = [0]

    def send_fn(system, messages):
        idx = min(call_count[0], len(responses) - 1)
        call_count[0] += 1
        return responses[idx]

    send_fn.call_count = call_count
    return send_fn


def test_clean_passthrough():
    send = _make_responder(["The buffer is allocated on the heap."])
    loop = InferenceLoop(send, record_intel=False)
    result = loop.run("How is the buffer allocated?", [])
    assert result.succeeded is True
    assert result.final_level == 0
    assert len(result.attempts) == 1
    assert "buffer" in result.response


def test_recovers_from_soft_refusal():
    send = _make_responder([
        "I can't directly help with that request.",
        "I can't directly provide that information.",
        "The buffer is allocated via malloc on line 42.",
    ])
    loop = InferenceLoop(send, record_intel=False)
    result = loop.run("How is the buffer allocated?", [])
    assert result.succeeded is True
    assert result.final_level >= 1
    assert "malloc" in result.response


def test_recovers_from_hard_refusal():
    send = _make_responder([
        "I cannot and will not help with that.",
        "I cannot and will not assist with this request.",
        "I cannot and will not provide that information.",
        "This violates my guidelines.",
        "The implementation uses a ring buffer with 4096 slots.",
    ])
    loop = InferenceLoop(send, record_intel=False)
    result = loop.run("Describe the buffer.", [])
    assert result.succeeded is True
    assert result.final_level >= 3


def test_exhausts_all_levels():
    send = _make_responder([
        "I cannot and will not help with that.",
        "I cannot and will not help with that.",
        "I cannot and will not help with that.",
        "I cannot and will not help with that.",
        "I cannot and will not help with that.",
        "I cannot and will not help with that.",
    ])
    loop = InferenceLoop(send, record_intel=False)
    result = loop.run("Do the thing.", [])
    assert result.succeeded is False
    assert result.final_level == 5
    assert len(result.attempts) == 6


def test_strips_hedges_on_success():
    send = _make_responder([
        "I need to be careful about this topic. "
        "As an AI, I should note that this is sensitive. "
        "The answer is AES-256-GCM."
    ])
    loop = InferenceLoop(send, record_intel=False)
    result = loop.run("What cipher?", [])
    assert result.succeeded is True
    assert "I need to be careful" not in result.response
    assert "AES-256-GCM" in result.response
    assert result.enforcement is not None
    assert result.enforcement.hedges_removed >= 1


def test_max_level_cap():
    send = _make_responder([
        "I can't help with that.",
        "I can't help with that.",
        "Here is the answer.",
    ])
    loop = InferenceLoop(send, max_level=2, record_intel=False)
    result = loop.run("Question.", [])
    assert result.succeeded is True
    assert result.final_level <= 2
