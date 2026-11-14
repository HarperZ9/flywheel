"""Native function calling records what the text protocol records.

The same tool call reaches the session two ways: as the provider's native
tool-call object, and as a `TOOL name {json}` line in the reply text. Both
must leave the same ledger entries, ask the same permission questions and run
the same tool. Replies are replayed from fixtures/provider_streams; no test
calls a provider. Wire-format sources are in harness/endpoints_tools_wire.py.
"""
import dataclasses
import json

import pytest

from harness.code_session.backends import build_agent
from harness.code_session.policy import DENIED_BY_MODE, DENIED_BY_USER, SessionExecutor
from harness.code_session.session import new_session
from harness.code_session.streaming import streamed_send
from harness.code_session.tool_specs import BUILTIN, for_executor
from harness.endpoints_tools import Reply, canonical, split_results
from tests.hosted_stream_fixtures import (NATIVE, PROVIDERS, backend, plain_object,
                                          stream_bytes)

TURN = ("user", "assistant", "tool_call", "tool_result", "approval")
ARGS = {"path": "n.txt", "content": "hi"}


def _session(tmp_path, provider, path, *, mode="ask", approver=None, streamed=False):
    """A session whose model answers one tool call, natively or as text, then finishes."""
    first = NATIVE[provider] if path == "native" else "turn1"
    names = (first, "turn2")
    made = backend(provider, plain=[] if streamed else [plain_object(provider, n) for n in names],
                   streams=[stream_bytes(provider, n) for n in names] if streamed else [])
    root = tmp_path / f"{provider}-{path}-{mode}-{int(streamed)}"
    root.mkdir(parents=True)
    asked = []

    def ask(name, args):
        asked.append((name, args))
        return (approver or (lambda n, a: "yes"))(name, args)
    session = new_session(build_agent([made]), str(root), mode=mode, approver=ask,
                          runner=lambda cmd, r: (True, "[exit 0]"))
    session.toolbox.mode = "on" if path == "native" else "off"
    return session, made, asked, root


def _records(session, kinds=TURN) -> list:
    return [dataclasses.asdict(e) for e in session.ledger.entries if e.kind in kinds]


def _requests(made) -> list:
    return [r["body"] for r in made.transport.requests + made.stream_transport.requests]


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_native_call_and_a_text_call_write_identical_ledger_entries(tmp_path, provider):
    native, native_backend, native_asked, native_root = _session(tmp_path, provider, "native")
    text, text_backend, text_asked, text_root = _session(tmp_path, provider, "text")
    first, second = native.turn("write a note"), text.turn("write a note")
    assert _records(native) == _records(text)            # content, meta, receipt ids, hashes
    assert [e.kind for e in native.ledger.entries] == [e.kind for e in text.ledger.entries]
    assert [e.kind for e in native.ledger.entries if e.kind in TURN] == \
        ["user", "assistant", "approval", "tool_call", "tool_result", "assistant"]
    assert native_asked == text_asked == [("write_file", ARGS)]
    assert first.final == second.final and first.steps == second.steps == 2
    assert (native_root / "n.txt").read_text() == (text_root / "n.txt").read_text() == "hi"
    assert native.agent.history == text.agent.history
    assert native.ledger.verify() and text.ledger.verify()
    # The two really did travel differently: schemas on one wire, none on the other.
    assert all("tools" in body for body in _requests(native_backend))
    assert not any("tools" in body for body in _requests(text_backend))
    # The one entry that differs says which wire was in use.
    configs = [json.loads(s.ledger.entries[-1].content) for s in (native, text)]
    assert [c.pop("native_tools") for c in configs] == ["on", "off"]
    assert configs[0] == configs[1]


@pytest.mark.parametrize("provider", PROVIDERS)
def test_the_comparison_fails_when_one_path_omits_the_authority_field(tmp_path, provider):
    """Control: `by` names who decided a call. Drop it on one path and the
    ledgers must stop comparing equal, or the test above proves nothing."""
    native, _b, _a, _r = _session(tmp_path, provider, "native")
    text, _b2, _a2, _r2 = _session(tmp_path, provider, "text")
    record = native.executor.on_decision
    native.executor.on_decision = lambda d: record({k: v for k, v in d.items() if k != "by"})
    native.turn("write a note")
    text.turn("write a note")
    assert _records(native) != _records(text)
    decisions = [json.loads(e.content) for e in text.ledger.entries if e.kind == "approval"]
    assert [d["by"] for d in decisions] == ["user:yes"]
    assert "by" not in json.loads(_records(native, ("approval",))[0]["content"])
    # Everything except the approval entry and the hashes chained after it still agrees.
    assert [r["content"] for r in _records(native, ("user", "assistant", "tool_call"))] == \
        [r["content"] for r in _records(text, ("user", "assistant", "tool_call"))]


CASES = [  # mode, approver answer, prompts expected, who decided, does the write happen
    ("ask", "yes", 1, "user:yes", True),
    ("ask", "no", 1, "user:no", False),
    ("ask", "always", 1, "user:always", True),
    ("edit", "no", 0, "mode:edit", True),
    ("auto", "no", 0, "mode:auto", True),
    ("plan", "yes", 0, "mode:plan", False),
]


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("mode, answer, prompts, by, written", CASES)
def test_permission_prompts_are_the_same_on_both_paths(tmp_path, provider, mode, answer,
                                                       prompts, by, written):
    seen = {}
    for path in ("native", "text"):
        session, _made, asked, root = _session(tmp_path, provider, path, mode=mode,
                                               approver=lambda n, a: answer)
        session.turn("write a note")
        decision = json.loads(_records(session, ("approval",))[0]["content"])
        result = _records(session, ("tool_result",))[0]["content"]
        seen[path] = (asked, decision, result, (root / "n.txt").exists())
        assert len(asked) == prompts and decision["by"] == by
        assert decision["decision"] == ("allow" if written else "deny")
        assert (root / "n.txt").exists() is written
        if not written:
            assert result == (DENIED_BY_MODE if mode == "plan" else DENIED_BY_USER)
    assert seen["native"] == seen["text"]


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_streamed_native_call_records_the_same_turn(tmp_path, provider):
    streamed, made, _asked, root = _session(tmp_path, provider, "native", streamed=True)
    text, _b, _a, _r = _session(tmp_path, provider, "text")
    shown = []
    with streamed_send(streamed.agent, shown.append):
        streamed.turn("write a note")
    text.turn("write a note")
    assert _records(streamed) == _records(text)
    assert 'TOOL write_file {"path": "n.txt", "content": "hi"}' in "".join(shown)
    assert (root / "n.txt").read_text() == "hi" and made.transport.requests == []


def test_results_go_back_in_each_providers_own_shape(tmp_path):
    sent = {}
    for provider in PROVIDERS:
        session, made, _asked, _root = _session(tmp_path, provider, "native")
        session.turn("write a note")
        sent[provider] = _requests(made)
        text, text_backend, _a, _r = _session(tmp_path, provider, "text")
        text.turn("write a note")
        assert "emitting lines in this exact format" in json.dumps(_requests(text_backend)[0])
    output = "wrote 2 bytes to n.txt"
    first, second = sent["anthropic"]
    assert {"name", "description", "input_schema"} == set(first["tools"][0])
    wire_system = first["system"][0]["text"]
    assert wire_system.endswith("do not write TOOL lines yourself.")
    assert "Tools are available through the function-calling interface." in wire_system
    assert "emitting lines in this exact format" not in wire_system     # text protocol wording
    assert "emitting lines in this exact format" in session.agent.system   # the record keeps it
    assert second["messages"][1] == {"role": "assistant",
                                     "content": plain_object("anthropic", "tool_use")["content"]}
    assert second["messages"][2] == {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "toolu_01FixtureWrite", "content": output}]}
    first, second = sent["openai"]
    write = [t for t in first["tools"] if t["function"]["name"] == "write_file"][0]
    assert write["type"] == "function" and write["function"]["parameters"]["required"] == \
        ["path", "content"]
    assert second["messages"][2]["tool_calls"][0]["id"] == "call_fixtureWrite01"
    assert second["messages"][3] == {"role": "tool", "tool_call_id": "call_fixtureWrite01",
                                     "content": "ok:\n" + output}
    first, second = sent["gemini"]
    assert "parametersJsonSchema" in first["tools"][0]["functionDeclarations"][0]
    assert second["contents"][1]["role"] == "model"
    assert second["contents"][1]["parts"] == \
        plain_object("gemini", "function_call")["candidates"][0]["content"]["parts"]
    assert second["contents"][2] == {"role": "user", "parts": [
        {"functionResponse": {"name": "write_file", "response": {"output": output}}}]}


def test_the_results_message_is_split_by_call_and_refused_when_it_does_not_fit():
    calls = [{"id": "a", "name": "read_file", "arguments": {"path": "x"}},
             {"id": "b", "name": "run", "arguments": {"cmd": "ls"}}]
    reply = Reply(canonical("Looking.", calls), "openai", None, calls)
    message = {"role": "user", "content": (
        "TOOL RESULTS:\nTOOL read_file -> ok:\nline one\n\nline three\n\n"
        "TOOL run -> FAIL:\n[exit 2]\n\nContinue if you need more tools, otherwise give "
        "the final answer with no TOOL line.")}
    assert split_results(message, reply) == [(True, "line one\n\nline three"), (False, "[exit 2]")]
    assert split_results({"role": "user", "content": "something else"}, reply) is None
    assert split_results({**message, "role": "assistant"}, reply) is None
    one = Reply(canonical("", calls[:1]), "openai", None, calls[:1])
    assert split_results(message, Reply(one.text, "openai", None, calls)) is None


def test_every_session_tool_has_a_schema_and_every_schema_has_a_tool(tmp_path):
    executor = SessionExecutor(root=str(tmp_path))
    for name in BUILTIN:
        assert callable(getattr(executor, f"_t_{name}", None)), name
    have = {m[3:] for m in dir(executor) if m.startswith("_t_")}
    assert have == set(BUILTIN)
    executor.external = {"mcp__docs__find": {"fn": None, "description": "find a page",
                                             "schema": {"type": "object", "properties": {}}},
                         "mcp__bad-name__x": {"fn": None, "description": ""},
                         "run": {"fn": None, "description": "shadows a built-in"}}
    names = [s["name"] for s in for_executor(executor)]
    assert "mcp__docs__find" in names and "mcp__bad-name__x" not in names
    assert names.count("run") == 1 and "task" not in names       # no task runner here
    executor.allowed_tools = frozenset({"read_file", "grep"})
    assert [s["name"] for s in for_executor(executor)] == ["read_file", "grep"]
