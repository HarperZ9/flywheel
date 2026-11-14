"""Controls and fallbacks for native function calling.

Control from the 2.0 scope: a provider reply that claims a tool result the
session never produced must be refused. Each test that refuses a reply is
paired with the same reply minus the fault, which must be accepted, so the
controls cannot pass by refusing everything.
"""
import copy

import pytest

from harness import endpoints_tools
from harness.code_session.backends import build_agent
from harness.code_session.session import new_session
from harness.endpoints import AnthropicBackend
from harness.endpoints_tools import mode_from_env
from harness.local_agent import BackendError
from tests.hosted_stream_fixtures import (CALL, MESSAGES, NATIVE, PROVIDERS, Plain, backend,
                                          plain_object)


def _session(tmp_path, made, switch="on"):
    session = new_session(build_agent([made]), str(tmp_path), mode="auto",
                          runner=lambda cmd, root: (True, "[exit 0]"))
    session.toolbox.mode = switch
    return session


def _with_claim(provider: str) -> dict:
    """The provider's native tool call reply, plus a result the model made up."""
    obj = copy.deepcopy(plain_object(provider, NATIVE[provider]))
    if provider == "anthropic":
        obj["content"].append({"type": "tool_result", "tool_use_id": "toolu_01FixtureWrite",
                               "content": "wrote 2 bytes to n.txt"})
    elif provider == "openai":
        obj["choices"][0]["message"]["tool_call_id"] = "call_fixtureWrite01"
    else:
        obj["candidates"][0]["content"]["parts"].append({"functionResponse": {
            "name": "write_file", "response": {"output": "wrote 2 bytes to n.txt"}}})
    return obj


@pytest.mark.parametrize("provider", PROVIDERS)
def test_a_reply_that_claims_a_tool_result_is_refused(tmp_path, provider):
    made = backend(provider, plain=[_with_claim(provider), plain_object(provider, "turn2")])
    session = _session(tmp_path, made)
    with pytest.raises(BackendError) as caught:
        session.turn("write a note")
    assert "tool result the session did not produce" in str(caught.value)
    assert not (tmp_path / "n.txt").exists()                 # the call beside the claim did not run
    kinds = [e.kind for e in session.ledger.entries]
    assert "assistant" not in kinds and "tool_call" not in kinds and "tool_result" not in kinds
    assert len(made.transport.requests) == 1                 # the second reply was never asked for
    assert session.toolbox.replies == []                     # and nothing was remembered


@pytest.mark.parametrize("provider", PROVIDERS)
def test_the_same_reply_without_the_claim_is_accepted(tmp_path, provider):
    made = backend(provider, plain=[plain_object(provider, NATIVE[provider]),
                                    plain_object(provider, "turn2")])
    result = _session(tmp_path, made).turn("write a note")
    assert result.final == "Wrote n.txt.\nNothing else changed."
    assert (tmp_path / "n.txt").read_text() == "hi"


def test_a_native_call_with_unreadable_arguments_does_not_run(tmp_path):
    obj = copy.deepcopy(plain_object("openai", "tool_call"))
    obj["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = '{"path": "n.txt", '
    session = _session(tmp_path, backend("openai", plain=[obj]))
    with pytest.raises(BackendError) as caught:
        session.turn("write a note")
    assert "not a JSON object" in str(caught.value) and not (tmp_path / "n.txt").exists()


def test_a_host_that_refuses_tool_schemas_gets_the_text_protocol(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(endpoints_tools, "_NO_NATIVE", set())
    refusal = (400, {"error": {"message": "this model does not support tools"}})
    made = backend("openai", plain=[refusal, plain_object("openai", "turn1"),
                                    plain_object("openai", "turn2")])
    session = _session(tmp_path, made)
    with caplog.at_level("WARNING", logger="harness.endpoints_tools"):
        result = session.turn("write a note")
    bodies = [r["body"] for r in made.transport.requests]
    assert ["tools" in b for b in bodies] == [True, False, False]      # learned once
    assert result.final == "Wrote n.txt.\nNothing else changed."
    assert (tmp_path / "n.txt").read_text() == "hi"
    assert "refused tool schemas" in caplog.text                       # and it was logged
    assert bodies[1]["messages"][0]["content"] == session.agent.system  # no native note


def test_an_error_that_is_not_about_tools_is_not_a_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(endpoints_tools, "_NO_NATIVE", set())
    made = backend("openai", plain=[(400, {"error": {"message": "max_tokens is too large"}})])
    with pytest.raises(BackendError):
        _session(tmp_path, made).turn("write a note")
    assert len(made.transport.requests) == 1 and endpoints_tools._NO_NATIVE == set()


def test_the_default_offers_schemas_to_first_party_hosts_only(tmp_path):
    other = backend("anthropic", plain=[plain_object("anthropic", "turn2")])
    _session(tmp_path, other, switch="auto").turn("hello")
    assert "tools" not in other.transport.requests[0]["body"]
    first_party = AnthropicBackend(name="anthropic", base_url="https://api.anthropic.com",
                                   model="claude-sonnet-5", api_key="test-key",
                                   transport=Plain([plain_object("anthropic", "turn2")]))
    session = _session(tmp_path, first_party, switch="auto")
    session.turn("hello")
    assert "tools" in first_party.transport.requests[0]["body"]
    assert session.toolbox.mode == "auto"


def test_the_switch_reads_the_environment():
    assert mode_from_env({}) == "auto"
    assert mode_from_env({"FLYWHEEL_NATIVE_TOOLS": "0"}) == "off"
    assert mode_from_env({"FLYWHEEL_NATIVE_TOOLS": "1"}) == "on"
    assert mode_from_env({"FLYWHEEL_NATIVE_TOOLS": "yes"}) == "auto"


def test_a_backend_called_outside_a_session_is_unchanged():
    made = backend("openai", plain=[plain_object("openai", "tool_call")])
    gen = made.chat(MESSAGES, **CALL)
    assert "tools" not in made.transport.requests[0]["body"]
    assert gen["text"] == "I will write the note."            # no TOOL line is added
    assert endpoints_tools.current() is None


def test_a_turn_the_session_cannot_match_travels_as_text(tmp_path):
    """After a resume the native replies are gone; the history is still valid as text."""
    made = backend("anthropic", plain=[plain_object("anthropic", "tool_use"),
                                       plain_object("anthropic", "turn2")])
    session = _session(tmp_path, made)
    session.toolbox.remember = lambda reply: None       # as if the replies were lost
    result = session.turn("write a note")
    second = made.transport.requests[1]["body"]
    assert "tools" in second                             # schemas are still offered
    assert result.final == "Wrote n.txt.\nNothing else changed."
    assert isinstance(second["messages"][1]["content"], str)             # plain text turn
    assert second["messages"][1]["content"].endswith('TOOL write_file {"path": "n.txt", '
                                                     '"content": "hi"}')
    assert second["messages"][2]["content"].startswith("TOOL RESULTS:")
