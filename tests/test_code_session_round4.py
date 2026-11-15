"""Coding session: findings R7 and R8 of the third independent review.

R7   a native tool call whose argument holds a lone surrogate ended the turn
     with a raw UnicodeEncodeError from the receipt hash. The reply is now
     refused as malformed, with a message that says why. Nothing runs either
     way, and the next turn works.
R8   a streamed OpenAI-format reply whose text is whitespace only and that
     carries a tool call was refused ("the text a stream showed differs from
     the reply it returned"). A plain reply of the same content was accepted
     as a pure tool-call turn; the streamed one now is too.

Recorded provider replies, replayed by a stub transport. No provider is called.
"""
import copy

import pytest

from harness import endpoints_tools
from harness.code_session.backends import build_agent
from harness.code_session.session import new_session
from harness.code_session.streaming import streamed_send
from harness.local_agent import BackendError
from tests.hosted_stream_fixtures import NATIVE, PROVIDERS, backend, plain_object, stream_bytes

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release

LONE = chr(0xD800)


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(endpoints_tools, "_NO_NATIVE", set())


def _session(tmp_path, provider, replies=(), streams=()):
    made = backend(provider, plain=list(replies), streams=list(streams))
    commands = []
    session = new_session(build_agent([made]), str(tmp_path), mode="auto",
                          runner=lambda cmd, root: (commands.append(cmd) or True, "[exit 0]"))
    session.toolbox.mode = "on"
    return session, made, commands


def _call_with(provider: str, content: str) -> dict:
    """The recorded native `write_file` reply with its `content` argument replaced."""
    obj = copy.deepcopy(plain_object(provider, NATIVE[provider]))
    if provider == "openai":
        import json
        function = obj["choices"][0]["message"]["tool_calls"][0]["function"]
        function["arguments"] = json.dumps({**json.loads(function["arguments"]),
                                            "content": content})
    elif provider == "anthropic":
        next(b for b in obj["content"] if b.get("type") == "tool_use")["input"]["content"] = content
    else:
        parts = obj["candidates"][0]["content"]["parts"]
        next(p for p in parts if "functionCall" in p)["functionCall"]["args"]["content"] = content
    return obj


def _text(provider: str, text: str) -> dict:
    obj = copy.deepcopy(plain_object(provider, "turn2"))
    if provider == "openai":
        obj["choices"][0]["message"]["content"] = text
    elif provider == "anthropic":
        obj["content"][0]["text"] = text
    else:
        obj["candidates"][0]["content"]["parts"][0]["text"] = text
    return obj


@pytest.mark.parametrize("provider", PROVIDERS)
def test_r7_a_native_call_with_a_lone_surrogate_is_refused_as_malformed(tmp_path, provider):
    session, _made, commands = _session(
        tmp_path, provider, [_call_with(provider, "hi " + LONE), _text(provider, "Done.")])
    with pytest.raises(BackendError, match="UTF-8"):
        session.turn("write a note")
    assert commands == [] and not (tmp_path / "n.txt").exists()
    assert [e for e in session.ledger.entries if e.kind == "tool_call"] == []
    assert session.turn("say done").final == "Done."            # the next turn works
    assert session.ledger.verify()


@pytest.mark.parametrize("provider", PROVIDERS)
def test_r7_control_the_same_call_with_a_whole_pair_runs(tmp_path, provider):
    session, _made, _commands = _session(
        tmp_path, provider, [_call_with(provider, "hi \U0001f600"), _text(provider, "Done.")])
    assert session.turn("write a note").final == "Done."
    assert (tmp_path / "n.txt").read_text(encoding="utf-8") == "hi \U0001f600"


def test_r8_a_streamed_reply_of_whitespace_and_a_tool_call_is_a_pure_tool_call_turn(tmp_path):
    recorded = stream_bytes("openai", "tool_call")
    swapped = (recorded.replace(b'"content":"I will wr"', b'"content":" \\n"')
               .replace(b'"content":"ite the n"', b'"content":""')
               .replace(b'"content":"ote."', b'"content":""'))
    assert swapped != recorded and b" \\n" in swapped
    session, _made, commands = _session(
        tmp_path, "openai", streams=[swapped, stream_bytes("openai", "turn2")])
    shown = []
    with streamed_send(session.agent, shown.append):
        result = session.turn("write a note")
    assert result.final and commands == []
    assert (tmp_path / "n.txt").read_text() == "hi"             # the native call ran
    calls = [e.content for e in session.ledger.entries if e.kind == "tool_call"]
    assert calls == ['write_file {"content": "hi", "path": "n.txt"}']
    first = next(e for e in session.ledger.entries if e.kind == "assistant")
    assert first.content.startswith("TOOL write_file "), "recorded with no prose, as a plain reply is"
    assert session.ledger.verify()
