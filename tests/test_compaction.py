"""test_compaction.py — context compaction is correct and re-checkable.

Success criteria (each test asserts one):
  - under budget: no-op, transcript byte-identical, verdict MATCH.
  - over budget: middle folds to one summary turn, head + tail preserved verbatim,
    tokens strictly drop.
  - the receipt re-checks (MATCH) and detects tampering of a kept turn or the
    summary (DRIFT).
  - an injected summarizer is the one used.
  - LocalAgent compacts its history opt-in, and not when the budget is unset.
"""
from harness import compaction
from harness.compaction import CompactionResult, compact, verify_compaction
from harness.local_agent import LocalAgent


def _msgs(n, filler="word " * 40):
    """n alternating turns, each large enough to blow a small token budget."""
    out = [{"role": "user", "content": "TASK: build the thing. " + filler}]
    for i in range(1, n):
        role = "assistant" if i % 2 else "user"
        out.append({"role": role, "content": f"turn {i} {filler}"})
    return out


def test_noop_when_under_budget():
    msgs = _msgs(4)
    res = compact(msgs, token_budget=10_000)
    assert res.compacted is False
    assert res.messages == msgs                      # unchanged, byte-identical
    assert res.receipt["method"] == "noop"
    assert verify_compaction(msgs, res)["verdict"] == "MATCH"


def test_folds_middle_and_preserves_head_and_tail():
    msgs = _msgs(20)
    res = compact(msgs, token_budget=200, keep_recent=4, keep_head=1)
    assert res.compacted is True
    # head (task anchor) and the last 4 turns are untouched
    assert res.messages[0] == msgs[0]
    assert res.messages[-4:] == msgs[-4:]
    # exactly one summary turn sits between head and tail
    assert len(res.messages) == 1 + 1 + 4
    assert res.messages[1]["content"].startswith("[compacted:")
    # the fold actually shrank the transcript
    assert res.receipt["tokens_after"] < res.receipt["tokens_before"]
    assert res.receipt["folded_turns"] == 20 - 1 - 4


def test_receipt_rechecks_and_detects_tampering():
    msgs = _msgs(20)
    res = compact(msgs, token_budget=200, keep_recent=4)
    assert verify_compaction(msgs, res)["verdict"] == "MATCH"

    # tamper a kept tail turn -> the fold no longer matches the source
    tampered_tail = CompactionResult(
        [dict(m) for m in res.messages], res.compacted, res.receipt)
    tampered_tail.messages[-1]["content"] += " INJECTED"
    v = verify_compaction(msgs, tampered_tail)
    assert v["verdict"] == "DRIFT"
    assert v["checks"]["tail_preserved"] is False

    # tamper the summary content -> summary hash breaks
    tampered_sum = CompactionResult(
        [dict(m) for m in res.messages], res.compacted, res.receipt)
    tampered_sum.messages[1]["content"] += " FORGED"
    v2 = verify_compaction(msgs, tampered_sum)
    assert v2["verdict"] == "DRIFT"
    assert v2["checks"]["summary_hash"] is False


def test_injected_summarizer_is_used():
    msgs = _msgs(20)
    res = compact(msgs, token_budget=200, keep_recent=4,
                  summarize=lambda folded: "STUBSUMMARY")
    assert "STUBSUMMARY" in res.messages[1]["content"]
    # the receipt still binds the real folded span, independent of the summarizer
    assert res.receipt["summarized_span_sha256"] is not None


class _FakeBackend:
    """A healthy backend that echoes a fixed completion (no network)."""
    name = "fake"

    def health(self):
        return True

    def chat(self, messages, *, system, max_tokens, temperature, seed):
        return {"text": "ok", "model_ref": "fake", "seed": seed}


def test_localagent_compacts_history_opt_in():
    agent = LocalAgent(backends=[_FakeBackend()], compact_budget=150,
                       compact_keep_recent=2)
    for i in range(8):
        agent.send("a longer user message number %d " % i + "word " * 30)
    # history was folded; a compaction receipt is recorded and re-checks
    assert agent.last_compaction is not None
    assert agent.last_compaction["method"] == "middle-fold"
    assert any(m["content"].startswith("[compacted:") for m in agent.history)


def test_localagent_no_compaction_when_budget_unset():
    agent = LocalAgent(backends=[_FakeBackend()])          # compact_budget defaults 0
    for i in range(8):
        agent.send("message %d " % i + "word " * 30)
    assert agent.last_compaction is None
    assert not any(m["content"].startswith("[compacted:") for m in agent.history)
