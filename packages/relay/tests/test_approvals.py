"""Per-step approval: a mutating tool call can be gated by an approve callback whose
decision is a hash-chained ledger entry bound to the call's exact bytes, so a stranger
re-derives that every mutating step was gated. Headless runs (no callback) record no
approvals and read NOT_GATED; a denied call never touches the tree yet is still gated."""
import json

from relay.approvals import (GATED, NOT_GATED, UNGATED, approval_verdict, call_hash,
                            is_mutating)
from relay.contract import Clause, Contract, evaluate
from relay.local_loop import run_agent
from relay.local_session import SessionLedger
from relay.local_tools import ToolExecutor, ToolGate
from relay.messages_api import make_receipt


class _Agent:
    def __init__(self, replies):
        self.system = "base"
        self._r = list(replies)

    def send(self, message):
        text = self._r.pop(0) if self._r else "done"
        rec = make_receipt(
            {"prompt": message, "system": self.system, "max_new_tokens": 512,
             "temperature": 0.0, "seed": 0, "requested_model": "stub"},
            {"text": text, "seed": 0}, "stub")
        return {"content": [{"type": "text", "text": text}], "backend": "stub", "x_receipt": rec}


def _ex(tmp_path):
    return ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=True))


def _edit_agent():
    return _Agent(['TOOL edit_file {"path": "m.py", "old": "a = 1", "new": "a = 2"}', "done"])


def _allow(name, args):
    return True


def _deny(name, args):
    return False


# --- the loop -------------------------------------------------------------

def test_headless_run_records_no_approvals_and_reads_not_gated(tmp_path):
    (tmp_path / "m.py").write_text("a = 1\n", encoding="utf-8")
    led = SessionLedger()
    result = run_agent(_edit_agent(), "bump a", _ex(tmp_path), led, max_steps=4)   # approve=None
    assert (tmp_path / "m.py").read_text() == "a = 2\n"           # applied, unchanged behavior
    assert result["approved"] == NOT_GATED
    assert not any(e.kind == "approval" for e in led.entries)


def test_approved_mutation_is_applied_and_binds_the_call_bytes(tmp_path):
    (tmp_path / "m.py").write_text("a = 1\n", encoding="utf-8")
    led = SessionLedger()
    result = run_agent(_edit_agent(), "bump a", _ex(tmp_path), led, max_steps=4, approve=_allow)
    assert (tmp_path / "m.py").read_text() == "a = 2\n"
    assert result["approved"] == GATED
    approvals = [e for e in led.entries if e.kind == "approval"]
    assert len(approvals) == 1 and approvals[0].meta["decision"] == "allow"
    assert approvals[0].content == call_hash(
        "edit_file", {"path": "m.py", "old": "a = 1", "new": "a = 2"})


def test_denied_mutation_never_touches_the_tree_but_is_still_gated(tmp_path):
    (tmp_path / "m.py").write_text("a = 1\n", encoding="utf-8")
    led = SessionLedger()
    result = run_agent(_edit_agent(), "bump a", _ex(tmp_path), led, max_steps=4, approve=_deny)
    assert (tmp_path / "m.py").read_text() == "a = 1\n"           # untouched
    assert result["approved"] == GATED                            # a deny is still a decision
    assert any(e.kind == "approval" and e.meta["decision"] == "deny" for e in led.entries)
    assert any("rejected" in e.content for e in led.entries if e.kind == "tool_result")


def test_read_only_turn_is_never_prompted(tmp_path):
    (tmp_path / "m.py").write_text("hi\n", encoding="utf-8")
    seen = []

    def approve(name, args):
        seen.append(name)
        return True

    led = SessionLedger()
    run_agent(_Agent(['TOOL read_file {"path": "m.py"}', "done"]),
              "read", _ex(tmp_path), led, max_steps=4, approve=approve)
    assert seen == [] and not any(e.kind == "approval" for e in led.entries)


def test_is_mutating_covers_every_write_tool_and_run():
    for t in ("write_file", "edit_file", "edit_lines", "edit_plan", "apply_diff", "run"):
        assert is_mutating(t)
    assert not is_mutating("read_file") and not is_mutating("repo_map")


# --- verdict re-derivation ------------------------------------------------

def _led(*rows):
    led = SessionLedger()
    for kind, content, meta in rows:
        led.append(kind, content, meta)
    return led


def test_ungated_when_a_mutation_has_no_matching_approval():
    led = _led(
        ("approval", call_hash("edit_file", {"path": "x"}), {"decision": "allow"}),
        ("tool_call", 'edit_file {"path": "y"}', {}),      # a different call: no matching approval
    )
    assert approval_verdict(led) == UNGATED


def test_gated_when_every_mutation_carries_its_allow():
    args = {"path": "x", "new": "z"}
    led = _led(
        ("approval", call_hash("edit_file", args), {"decision": "allow"}),
        ("tool_call", f"edit_file {json.dumps(args, sort_keys=True)}", {}),
    )
    assert approval_verdict(led) == GATED


def test_not_gated_without_any_approval_entries():
    assert approval_verdict(_led(("tool_call", 'edit_file {"path": "x"}', {}))) == NOT_GATED


# --- contract clause ------------------------------------------------------

def test_steps_approved_clause_maps_the_verdict():
    c = Contract((Clause("steps_approved"),))
    assert evaluate(c, {"approval_verdict": "GATED"})["verdict"] == "ALLOW"
    assert evaluate(c, {"approval_verdict": "UNGATED"})["verdict"] == "REFUTED"
    assert evaluate(c, {"approval_verdict": "NOT_GATED"})["verdict"] == "UNVERIFIABLE"
