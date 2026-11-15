"""Context compaction: when the prompt grows past a token budget, fold the middle of
the history into one summary turn, keep the task anchor and recent turns verbatim, and
NEVER fold pinned policy text. The fold is witnessed: its receipt binds the folded-span
and summary hashes, verify_compaction re-checks them, and the loop records the receipt
on the hash-chained ledger while the untruncated trajectory stays on that ledger."""
import json

from relay.compaction import (CompactionResult, compact, lexrank_summary,
                              total_tokens, verify_compaction)
from relay.local_loop import run_agent
from relay.local_session import SessionLedger
from relay.local_tools import ToolExecutor, ToolGate
from relay.messages_api import make_receipt


def _msgs(n):
    # n user/assistant turns with enough text to blow a tiny budget
    out = [{"role": "user", "content": "the task is to refactor the parser module"}]
    for i in range(n):
        out.append({"role": "assistant", "content": f"step {i}: I read and edited file number {i}"})
        out.append({"role": "user", "content": f"tool result number {i}: ok, proceed to the next"})
    return out


# --- the fold -------------------------------------------------------------

def test_within_budget_is_a_noop():
    msgs = _msgs(2)
    res = compact(msgs, token_budget=10_000)
    assert res.compacted is False and res.messages == msgs
    assert res.receipt["method"] == "noop"


def test_over_budget_folds_the_middle_and_shrinks():
    msgs = _msgs(20)
    before = total_tokens(msgs)
    res = compact(msgs, token_budget=50, keep_recent=4)
    assert res.compacted is True
    assert res.receipt["tokens_after"] < before
    assert res.messages[0] == msgs[0]                     # task anchor kept
    assert res.messages[-4:] == msgs[-4:]                 # recent turns kept verbatim
    assert res.receipt["folded_turns"] > 0


def test_pinned_policy_text_is_never_folded():
    msgs = _msgs(20)
    policy = {"role": "system", "content": "POLICY: never edit tests/*"}
    msgs.insert(5, policy)
    res = compact(msgs, token_budget=50, keep_recent=4)
    assert res.compacted is True
    assert policy in res.messages                          # survived the fold verbatim
    assert res.receipt["pinned_kept"] >= 1


# --- the fold is re-checkable ---------------------------------------------

def test_verify_compaction_matches_an_honest_fold():
    res = compact(_msgs(20), token_budget=50, keep_recent=4)
    v = verify_compaction(_msgs(20), res)
    assert v["verdict"] == "MATCH" and all(v["checks"].values())


def test_verify_compaction_drifts_on_a_tampered_summary():
    orig = _msgs(20)
    res = compact(orig, token_budget=50, keep_recent=4)
    kh, pc = res.receipt["kept_head"], res.receipt["pinned_kept"]
    res.messages[kh + pc]["content"] += " (secretly altered)"   # tamper the inserted summary
    v = verify_compaction(orig, res)
    assert v["verdict"] == "DRIFT" and v["checks"]["summary_hash"] is False


def test_lexrank_summary_is_deterministic():
    msgs = _msgs(20)
    assert lexrank_summary(msgs) == lexrank_summary(msgs)      # no model, no randomness


# --- witnessed in the loop ------------------------------------------------

class _HistoryAgent:
    """A fake agent that grows its own history like LocalAgent, so the loop's
    compaction path has something to fold."""

    def __init__(self, replies, seed_turns=0):
        self.system = "base"
        self._r = list(replies)
        self.history = _msgs(seed_turns) if seed_turns else []

    def send(self, message):
        self.history.append({"role": "user", "content": message})
        text = self._r.pop(0) if self._r else "done"
        self.history.append({"role": "assistant", "content": text})
        rec = make_receipt(
            {"prompt": message, "system": self.system, "max_new_tokens": 512,
             "temperature": 0.0, "seed": 0, "requested_model": "stub"},
            {"text": text, "seed": 0}, "stub")
        return {"content": [{"type": "text", "text": text}], "backend": "stub", "x_receipt": rec}


def _ex(tmp_path):
    return ToolExecutor(root=str(tmp_path), gate=ToolGate())


def test_a_fold_is_witnessed_on_the_ledger(tmp_path):
    agent = _HistoryAgent(["done"], seed_turns=20)            # already over a tiny budget
    led = SessionLedger()
    result = run_agent(agent, "finish up", _ex(tmp_path), led, max_steps=2, compact_budget=30)
    comp = [e for e in led.entries if e.kind == "compaction"]
    assert len(comp) == 1                                     # the fold was recorded
    assert comp[0].meta["schema"] == "relay.compaction/v1"
    assert comp[0].meta["tokens_after"] < comp[0].meta["tokens_before"]
    assert led.verify() and result["chain_ok"]               # the chain still re-derives


def test_no_budget_means_no_compaction_entry(tmp_path):
    agent = _HistoryAgent(["done"], seed_turns=20)
    led = SessionLedger()
    run_agent(agent, "finish up", _ex(tmp_path), led, max_steps=2)   # compact_budget=0
    assert not any(e.kind == "compaction" for e in led.entries)
