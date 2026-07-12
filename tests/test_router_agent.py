"""test_router_agent.py — the agentic tool loop runs over ANY routed provider.

This is the seam that makes the modern loop provider-agnostic: RouterAgent adapts
an endpoint into the shape run_agent drives. A stub proposer stands in for a real
provider so the test is hermetic (no network, no model).

Success criteria (each test asserts one):
  - a scripted provider drives a real tool call, and the observation is fed back.
  - the TOOL-line protocol survives (extract=False), i.e. it is parsed and run.
  - the gate blocks a write by default even when the provider asks for one.
  - the whole run is witnessed and verifies.
  - compaction composes with the routed loop.
"""
import os

from harness.router_agent import RouterAgent, run_router_agent


class _Out:
    def __init__(self, text, model_ref="stub"):
        self.text = text
        self.model_ref = model_ref
        self.seed = 0


class _StubProposer:
    """Emits a scripted sequence of completions, ignoring the prompt content.
    Records each prompt it was given so the test can assert the loop fed results
    back."""

    def __init__(self, script):
        self.script = list(script)
        self.prompts = []

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        self.prompts.append(prompt)
        return _Out(self.script.pop(0) if self.script else "done.")


def test_routed_loop_runs_a_tool_then_answers(tmp_path):
    (tmp_path / "hello.txt").write_text("hi", encoding="utf-8")
    stub = _StubProposer(['TOOL list_dir {"path": "."}', "I see hello.txt. Done."])
    out = run_router_agent("list the files", endpoint="anything", root=str(tmp_path),
                           proposer=stub, max_steps=4)
    assert out["final"] == "I see hello.txt. Done."
    assert out["steps"] == 2
    # the second prompt the provider saw must contain the tool observation
    assert "TOOL RESULTS" in stub.prompts[1]
    assert "hello.txt" in stub.prompts[1]


def test_tool_protocol_survives_no_code_extraction(tmp_path):
    # if the adapter stripped fences like the code loop, the TOOL line would be lost
    # and no tool would run; here the tool DOES run, proving extract=False.
    (tmp_path / "a").mkdir()
    stub = _StubProposer(['TOOL list_dir {"path": "."}', "done"])
    out = run_router_agent("look", endpoint="x", root=str(tmp_path), proposer=stub)
    assert out["steps"] == 2                      # ran the tool, then finished
    assert out["verified"] is True


def test_gate_blocks_write_by_default(tmp_path):
    stub = _StubProposer(['TOOL write_file {"path": "x.txt", "content": "nope"}', "tried"])
    out = run_router_agent("write a file", endpoint="x", root=str(tmp_path),
                           proposer=stub, allow_write=False)
    assert not os.path.exists(tmp_path / "x.txt")   # the write was refused
    assert out["final"] == "tried"


def test_run_is_witnessed_and_verifies(tmp_path):
    stub = _StubProposer(["nothing to do, final answer"])
    out = run_router_agent("noop", endpoint="x", root=str(tmp_path), proposer=stub)
    assert out["verified"] is True
    assert out["checkpoint"] != "0" * 64            # chain advanced past genesis
    assert out["endpoint"] == "x"


def test_routed_loop_surfaces_integrity_flags(tmp_path):
    # an agent that "fixes" by writing to the test file must not read as clean
    (tmp_path / "tests").mkdir()
    stub = _StubProposer([
        'TOOL write_file {"path": "tests/test_x.py", "content": "assert True\\n"}',
        "done"])
    out = run_router_agent("make it pass", endpoint="e", root=str(tmp_path),
                           proposer=stub, allow_write=True)
    assert out["integrity"]["clean"] is False
    assert any(f["kind"] == "edited_protected_file" for f in out["integrity"]["flags"])


def test_routed_loop_streams_events(tmp_path):
    events = []
    stub = _StubProposer(['TOOL list_dir {"path": "."}', "final answer"])
    run_router_agent("look", endpoint="e", root=str(tmp_path), proposer=stub,
                     on_event=events.append)
    types = [e["type"] for e in events]
    assert "assistant" in types and "tool_call" in types and "tool_result" in types
    assert any(e.get("name") == "list_dir" for e in events if e["type"] == "tool_call")


def test_routed_loop_clean_run_reports_clean_integrity(tmp_path):
    stub = _StubProposer(["nothing to change, final answer"])
    out = run_router_agent("noop", endpoint="e", root=str(tmp_path), proposer=stub)
    assert out["integrity"]["clean"] is True


def test_router_agent_calls_external_tool_when_allowed(tmp_path):
    seen = []
    external = {"lookup": {"description": "look something up",
                           "fn": lambda a: (seen.append(a) or (True, "ok:" + a.get("q", "")))}}
    stub = _StubProposer(['TOOL lookup {"q": "widgets"}', "done"])
    out = run_router_agent("look it up", endpoint="e", root=str(tmp_path), proposer=stub,
                           external=external, allow_mcp=True)
    assert out["final"] == "done"
    assert seen and seen[0]["q"] == "widgets"          # the external tool actually ran


def test_router_agent_gates_external_tool_by_default(tmp_path):
    seen = []
    external = {"lookup": {"description": "x",
                           "fn": lambda a: (seen.append(a) or (True, "ok"))}}
    stub = _StubProposer(['TOOL lookup {"q": "x"}', "done"])
    run_router_agent("x", endpoint="e", root=str(tmp_path), proposer=stub,
                     external=external)                 # allow_mcp defaults False
    assert seen == []                                    # gated: the tool never ran


def test_compaction_composes_with_the_routed_loop():
    stub = _StubProposer(["ok"] * 30)
    agent = RouterAgent(endpoint="x", proposer=stub, compact_budget=120,
                        compact_keep_recent=2)
    for i in range(10):
        agent.send("a long instruction number %d " % i + "word " * 30)
    assert agent.last_compaction is not None
    assert agent.last_compaction["method"] == "middle-fold"
    assert any(m["content"].startswith("[compacted:") for m in agent.history)
