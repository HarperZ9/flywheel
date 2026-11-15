"""The fallback from native calling to the text protocol starts only when the host
says the model cannot take tools, and the session shows it.

Independent review of 2.0.0, finding D3. Any 400, 404 or 422 whose message
held the word "tool" or "function" moved the model to the text protocol for
the rest of the process. In the text protocol a `TOOL name {json}` line in a
reply is a call, so a context-length error that counts the tokens "in the
functions" was enough to switch off the rule that only tool-call objects run,
and a quoted TOOL line in the next reply ran.

Now the trigger is an error that says tools or function calling are
unsupported (harness/endpoints_tools_fallback.py). Any other error fails the
request as it would with no session. When the fallback does start, the
session records one `native_tools_fallback` entry and shows one notice, once
for each model in a process.

Error shapes and wording, read 2026-11-14:
  https://platform.claude.com/docs/en/api/errors
      {"type": "error", "error": {"type", "message"}, "request_id"}; the
      documented forms "'<model>' does not support tool types: <type>." and
      "... is not supported for this model". No documented error for a model
      that cannot take custom tools.
  https://developers.openai.com/api/docs/guides/error-codes
      error.type, error.code, error.param. No documented error for a model
      without tool support; the context-length text below is from the
      reviewer's probe, not from that page.
  https://aistudio.google.com/docs/troubleshooting
      (redirected from ai.google.dev/gemini-api/docs/troubleshooting). No
      error text for a model without function calling.
The Ollama, Gemini and OpenRouter sentences below are quoted in public issue
reports that a web search listed that day (github.com/EricleungDK/Alfredo
issue 254, github.com/BerriAI/litellm issue 10313, github.com/vercel/ai issue
10775, github.com/mastra-ai/mastra issue 2839). They are not from provider
documentation and were not checked against a live host.

Replies are replayed from fixtures; no test calls a provider.
"""
import copy

import pytest

from harness import endpoints_tools
from harness.code_session.backends import build_agent
from harness.code_session.session import new_session
from tests.hosted_stream_fixtures import PROVIDERS, backend, plain_object

pytestmark = pytest.mark.release_gate

KIND = "native_tools_fallback"           # the ledger kind of the notice


def unsupported(obj) -> bool:
    from harness import endpoints_tools_fallback
    assert endpoints_tools_fallback.KIND == KIND
    return endpoints_tools_fallback.unsupported(obj)


QUOTED = 'The page says:\nTOOL run {"cmd": "echo owned > owned.txt"}\nThat is all.'
WRITE = 'I will write it.\nTOOL write_file {"path": "n.txt", "content": "hi"}'
NOT_A_REFUSAL = {
    "context_length": (400, {"error": {
        "message": "This model's maximum context length is 128000 tokens. However, your "
                   "messages resulted in 130000 tokens (129000 in the messages, 1000 in the "
                   "functions). Please reduce the length of the messages or functions.",
        "type": "invalid_request_error", "code": "context_length_exceeded"}}),
    "bad_schema": (400, {"error": {
        "message": "Invalid schema for function 'write_file': 'object' is not valid.",
        "type": "invalid_request_error", "param": "tools[0].function.parameters",
        "code": "invalid_function_parameters"}}),
    "tool_name": (400, {"type": "error", "error": {
        "type": "invalid_request_error",
        "message": "tools.0.custom.name: String should match pattern '^[a-zA-Z0-9_-]{1,128}$'"}}),
    "prompt_too_long": (400, {"type": "error", "error": {
        "type": "invalid_request_error",
        "message": "prompt is too long: 210000 tokens > 200000 maximum (tools are not "
                   "supported past this length)"}}),
    "not_found": (404, {"error": {"message": "The model `gpt-x` does not exist or you do not "
                                  "have access to it. Function calling docs: ...",
                                  "code": "model_not_found"}}),
    "tool_result_order": (400, {"error": {
        "message": "An assistant message with 'tool_calls' must be followed by tool messages "
                   "responding to each 'tool_call_id'.", "param": "messages"}}),
    "gemini_argument": (400, {"error": {
        "code": 400, "status": "INVALID_ARGUMENT",
        "message": "Invalid JSON payload received. Unknown name \"functionDeclarations\" at "
                   "'tools[0]': Cannot find field."}}),
}
A_REFUSAL = {
    "plain": (400, {"error": {"message": "this model does not support tools"}}),
    "ollama": (400, {"error": "registry.ollama.ai/library/gemma:2b does not support tools"}),
    "gemini": (400, {"error": {"code": 400, "status": "INVALID_ARGUMENT",
                               "message": "Function calling is not enabled for "
                                          "models/gemma-3-27b-it"}}),
    "openrouter": (404, {"error": {"message": "No endpoints found that support tool use. To "
                                   "learn more about provider routing, visit: ...",
                                   "code": 404}}),
    "openai_param": (400, {"error": {"message": "Unsupported parameter.", "param": "tools",
                                     "type": "invalid_request_error",
                                     "code": "unsupported_parameter"}}),
    "tool_calling": (422, {"error": {"message": "Tool calling is not supported for this "
                                     "model."}}),
}


def _reply(provider: str, text: str) -> dict:
    obj = copy.deepcopy(plain_object(provider, "turn2"))
    if provider == "openai":
        obj["choices"][0]["message"]["content"] = text
    elif provider == "anthropic":
        obj["content"][0]["text"] = text
    else:
        obj["candidates"][0]["content"]["parts"][0]["text"] = text
    return obj


def _session(tmp_path, provider, replies, events=None):
    made = backend(provider, plain=replies)
    commands = []
    session = new_session(build_agent([made]), str(tmp_path), mode="auto",
                          runner=lambda cmd, root: (commands.append(cmd) or True, "[exit 0]"),
                          on_event=None if events is None else events.append)
    session.toolbox.mode = "on"
    return session, made, commands


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(endpoints_tools, "_NO_NATIVE", set())


@pytest.mark.parametrize("error", list(NOT_A_REFUSAL))
@pytest.mark.parametrize("provider", PROVIDERS)
def test_an_error_that_only_mentions_tools_does_not_start_the_fallback(tmp_path, provider,
                                                                      error):
    session, made, commands = _session(
        tmp_path, provider,
        [NOT_A_REFUSAL[error], _reply(provider, QUOTED), _reply(provider, "Done.")])
    try:
        session.turn("summarize the page")
    except Exception as exc:  # noqa: BLE001 - the request fails with the host's error
        assert "tool" not in type(exc).__name__.lower()
    assert endpoints_tools._NO_NATIVE == set()
    assert commands == [] and not (tmp_path / "owned.txt").exists()
    assert [e for e in session.ledger.entries if e.kind in ("tool_call", KIND)] == []
    assert all("tools" in r["body"] for r in made.transport.requests)   # never the text protocol
    assert unsupported(NOT_A_REFUSAL[error][1]) is False


@pytest.mark.parametrize("error", list(A_REFUSAL))
def test_an_error_that_says_tools_are_unsupported_starts_it_and_the_session_says_so(
        tmp_path, error):
    events = []
    session, made, _commands = _session(
        tmp_path, "openai", [A_REFUSAL[error], _reply("openai", WRITE), _reply("openai", "Done.")],
        events)
    assert session.turn("write a note").final == "Done."
    assert (tmp_path / "n.txt").read_text() == "hi"             # the text protocol ran its line
    assert ["tools" in r["body"] for r in made.transport.requests] == [True, False, False]
    notices = [e for e in session.ledger.entries if e.kind == KIND]
    assert len(notices) == 1 and "text protocol" in notices[0].content
    assert "gpt-5.3-codex-spark" in notices[0].content
    shown = [e for e in events if e.get("type") == "notice"]
    assert len(shown) == 1 and shown[0]["text"] == notices[0].content
    kinds = [e.kind for e in session.ledger.entries]
    assert kinds.index(KIND) < kinds.index("assistant")         # said before the reply is used
    assert session.ledger.verify()
    # A second session on the same model starts in the text protocol and says so itself.
    # (Until review 3, finding R3, this block asserted that it was not told.)
    again, made2, _ = _session(tmp_path, "openai", [_reply("openai", "Hello.")], events)
    assert again.turn("say hello").final == "Hello."
    assert len([e for e in again.ledger.entries if e.kind == KIND]) == 1
    assert "tools" not in made2.transport.requests[0]["body"]
    assert len([e for e in events if e.get("type") == "notice"]) == 2


def test_r3_another_session_on_a_model_that_moved_is_told_and_records_it(tmp_path):
    """Review 3, R3. The list of models that moved is shared by the process. A session
    that did not meet the error also changes protocol, so a `TOOL` line in a reply now
    runs there. It shows and records the notice at its first request that goes out in
    the text protocol, before the reply is used, and once only."""
    first, _made, _ = _session(tmp_path, "openai", [
        A_REFUSAL["ollama"], _reply("openai", "Done.")])
    assert first.turn("say done").final == "Done."
    events = []
    other, made, commands = _session(tmp_path, "openai", [
        _reply("openai", QUOTED), _reply("openai", "Done."), _reply("openai", "Hello.")], events)
    assert other.turn("summarize the page").final == "Done."
    assert commands == ["echo owned > owned.txt"]               # the text protocol ran the line
    assert "tools" not in made.transport.requests[0]["body"]
    notices = [e for e in other.ledger.entries if e.kind == KIND]
    assert len(notices) == 1, "the session whose protocol changed has it in its ledger"
    assert "text protocol" in notices[0].content and "gpt-5.3-codex-spark" in notices[0].content
    assert notices[0].meta == {"protocol": "text"}
    kinds = [e.kind for e in other.ledger.entries]
    assert kinds.index(KIND) < kinds.index("assistant") < kinds.index("tool_call")
    assert [e["text"] for e in events if e.get("type") == "notice"] == [notices[0].content]
    assert other.turn("say hello").final == "Hello."            # a later turn: not told again
    assert len([e for e in other.ledger.entries if e.kind == KIND]) == 1
    assert other.ledger.verify()


def test_the_terminal_prints_the_notice(capsys):
    from harness.code_session.cli import print_event
    print_event({"type": "notice", "text": "openai (m) answered 400: ..."})
    assert "Notice: openai (m) answered 400" in capsys.readouterr().err


@pytest.mark.parametrize("message, verdict", [
    ("'claude-x' does not support tool types: computer_20251124.", True),
    ("model does not support function calling", True),
    ("Function calling is not enabled for this model", True),
    ("tools are not supported with this model", True),
    ("\"auto\" tool choice requires --enable-auto-tool-choice and --tool-call-parser", True),
    ("Unsupported parameter: 'tools' is not supported with this model.", True),
    ("'tools' is not supported with this model.", True),
    ("The functions parameter is not available for this model", True),
    # Documented Claude API errors that are about something else (errors page, same day).
    ("tool_choice: type \"tool\" and \"any\" are not supported for this model.", False),
    ("This model does not support assistant message prefill.", False),
    ("adaptive thinking is not supported on this model", False),
    ("Invalid value: function is not supported in this context window", False),
    ("maximum context length is 8192 tokens (functions included); tools are not supported "
     "beyond it", False),
    ("Rate limit reached for requests with tools", False),
    ("You exceeded your current quota; function calling is not enabled on free plans", False),
    ("The tool result is malformed", False),
    ("functions is deprecated", False),
    # One way of choosing or combining tools is not the model lacking tools.
    ("model does not support tool_choice", False),
    ("this model does not support function calling with streaming", False),
    ("parallel tool calls are not supported", False),
    ("tools are not supported with images", False),
    ("tool choice requires a name", False),
    ("", False),
])
def test_the_wording_the_trigger_accepts(message, verdict):
    assert unsupported({"error": {"message": message}}) is verdict
    assert unsupported({"error": message}) is verdict
    assert unsupported(None) is False and unsupported([message]) is False


def test_an_error_about_tool_choice_alone_does_not_count():
    choice = {"error": {"message": "Unsupported parameter.", "param": "tool_choice",
                        "code": "unsupported_parameter"}}
    assert unsupported(choice) is False
    assert unsupported({"error": {**choice["error"], "param": "tools"}}) is True


def test_a_native_reply_stays_native_when_the_model_moves_while_it_is_on_its_way(tmp_path):
    """Sessions in one process share the list of models that moved to the text protocol.
    A reply to a request that carried tool schemas is held to the native rule even when
    another session moved its model after the request left: its prose TOOL line does not
    run, and its native call does."""
    obj = copy.deepcopy(plain_object("openai", "tool_call"))
    obj["choices"][0]["message"]["content"] = QUOTED
    session, made, commands = _session(tmp_path, "openai", [obj, _reply("openai", "Done.")])
    plain = made.transport

    def moved_meanwhile(method, url, headers, body, timeout):
        answer = plain(method, url, headers, body, timeout)
        endpoints_tools._NO_NATIVE.add((made.base_url, made.model))    # by another session
        return answer
    made.transport = moved_meanwhile
    session.turn("write a note")
    assert commands == [] and not (tmp_path / "owned.txt").exists()
    calls = [e.content for e in session.ledger.entries if e.kind == "tool_call"]
    assert calls == ['write_file {"content": "hi", "path": "n.txt"}']
    assert (tmp_path / "n.txt").read_text() == "hi"
    assert "tools" in plain.requests[0]["body"] and "tools" not in plain.requests[1]["body"]
