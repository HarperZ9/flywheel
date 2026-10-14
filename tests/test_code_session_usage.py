"""Falsifiers: provider token counts reach the session, and -p speaks JSON."""
import json

import pytest

from harness import token_usage
from harness.code_session import cli, slash
from harness.code_session.backends import build_agent
from harness.code_session.print_mode import run_print
from harness.code_session.session import new_session
from harness.endpoints import AnthropicBackend, GeminiBackend, OpenAICompatBackend
from tests.test_code_session import ScriptBackend, _bare_runner


def _transport(obj):
    return lambda method, url, headers, body, timeout: (200, obj)


def test_readers_take_only_whole_integer_pairs():
    assert token_usage.from_openai({"usage": {"prompt_tokens": 3, "completion_tokens": 4}}) == \
        {"input_tokens": 3, "output_tokens": 4}
    assert token_usage.from_anthropic({"usage": {"input_tokens": 5, "output_tokens": 6}}) == \
        {"input_tokens": 5, "output_tokens": 6}
    assert token_usage.from_gemini({"usageMetadata": {"promptTokenCount": 7,
                                                      "candidatesTokenCount": 8}}) == \
        {"input_tokens": 7, "output_tokens": 8}
    assert token_usage.from_ollama({"prompt_eval_count": 1, "eval_count": 2}) == \
        {"input_tokens": 1, "output_tokens": 2}
    for bad in ({}, {"usage": {"prompt_tokens": 3}}, {"usage": {"prompt_tokens": -1,
                                                                "completion_tokens": 2}},
                {"usage": {"prompt_tokens": "3", "completion_tokens": 2}}, None):
        assert token_usage.from_openai(bad) is None


@pytest.mark.parametrize("backend, obj", [
    (OpenAICompatBackend(name="o", base_url="http://x", model="m", api_key="k"),
     {"choices": [{"message": {"content": "hi"}}],
      "usage": {"prompt_tokens": 11, "completion_tokens": 2}}),
    (AnthropicBackend(name="a", base_url="http://x", model="m", api_key="k"),
     {"content": [{"type": "text", "text": "hi"}],
      "usage": {"input_tokens": 11, "output_tokens": 2}}),
    (GeminiBackend(name="g", base_url="http://x", model="m", api_key="k"),
     {"candidates": [{"content": {"parts": [{"text": "hi"}]}}],
      "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 2}}),
])
def test_hosted_backends_pass_provider_tokens_through_the_agent(backend, obj):
    backend.transport = _transport(obj)
    agent = build_agent([backend])
    resp = agent.send("hello")
    assert resp["x_token_usage"] == {"input_tokens": 11, "output_tokens": 2}


def test_a_response_without_counts_carries_none():
    b = OpenAICompatBackend(name="o", base_url="http://x", model="m", api_key="k",
                            transport=_transport({"choices": [{"message": {"content": "hi"}}]}))
    assert "x_token_usage" not in build_agent([b]).send("hello")


class CountingBackend(ScriptBackend):
    def chat(self, messages, **kw):
        out = super().chat(messages, **kw)
        out["token_usage"] = {"input_tokens": 100, "output_tokens": 10}
        return out


def test_session_totals_tokens_and_counts_uncounted_calls(tmp_path):
    s = new_session(build_agent([CountingBackend(['TOOL list_dir {"path": "."}', "done"])]),
                    str(tmp_path), mode="auto", runner=_bare_runner)
    r = s.turn("look")
    assert r.usage == {"model_calls": 2, "input_tokens": 200, "output_tokens": 20,
                       "uncounted_calls": 0}
    plain = new_session(build_agent([ScriptBackend(["ok"])]), str(tmp_path), mode="auto",
                        runner=_bare_runner)
    plain.turn("hi")
    assert plain.usage["uncounted_calls"] == 1 and plain.usage["input_tokens"] == 0
    assert "not estimated" in slash.dispatch(plain, "/cost")
    assert "200 input and 20 output tokens" in slash.dispatch(s, "/cost")


def test_json_output_is_one_result_object(tmp_path, capsys):
    s = new_session(build_agent([CountingBackend(["The answer."])]), str(tmp_path),
                    mode="auto", runner=_bare_runner)
    assert run_print(s, "q", "json") == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1
    result = json.loads(lines[0])
    assert result["schema"] == "flywheel.code-result/v1" and result["final"] == "The answer."
    assert result["chain_ok"] is True and result["usage"]["input_tokens"] == 100


def test_stream_json_emits_events_then_the_result(tmp_path, capsys):
    s = new_session(build_agent([ScriptBackend(['TOOL list_dir {"path": "."}', "done"])]),
                    str(tmp_path), mode="auto", runner=_bare_runner)
    run_print(s, "look", "stream-json")
    rows = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]
    kinds = [r.get("type") for r in rows]
    assert kinds[-1] == "result" and "event" in kinds
    assert any(r.get("name") == "list_dir" for r in rows if r["type"] == "event")


def test_output_format_flag_parses():
    assert cli.parse_args(["-p", "x", "--output-format", "stream-json"]).output_format == \
        "stream-json"
