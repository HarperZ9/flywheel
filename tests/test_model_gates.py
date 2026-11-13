"""Falsifiers for the request and server gates around an absent figure.

Hermetic: literal request dicts and argv lists, no server and no network.
Load-bearing: (1) a streamed OpenAI call without stream_options.include_usage
reports null usage on every chunk, so every count is absent and the cause is the
request rather than the provider; (2) a non-streaming call is NOT excused by
that gate, so a genuine provider silence stays visible; (3) a launch flag nobody
told us about is unknown and never assumed open OR shut; (4) Gemini gates the
thought text and not the thought token count, so one absence is explained and
the other is not.
"""
from harness import model_gates as mg
from harness.model_dialects import GEMINI, OLLAMA, OPENAI, OPENAI_RESPONSES


def _state(reading, name):
    return next(g["state"] for g in reading["gates"] if g["gate"] == name)


# --- the streaming usage gate -----------------------------------------------

def test_a_streamed_call_without_the_flag_explains_every_absent_count():
    """The highest-impact gate: usage is null on every chunk unless asked for,
    so a receipt built from that stream says zero tokens for a real spend."""
    reading = mg.check({"stream": True, "model": "gpt-4o"}, dialect=OPENAI)
    assert _state(reading, "stream_usage") == mg.SHUT
    assert reading["all_open"] is False
    for meaning in ("input", "output", "cache_read", "reasoning"):
        why = mg.why_absent(reading, meaning)
        assert why["explained"] is True
        assert why["by"] == ["stream_usage"]


def test_the_flag_opens_the_gate_and_stops_excusing_the_absence():
    reading = mg.check({"stream": True, "stream_options": {"include_usage": True}},
                       dialect=OPENAI)
    assert _state(reading, "stream_usage") == mg.OPEN
    assert reading["all_open"] is True
    assert mg.why_absent(reading, "input")["explained"] is False


def test_a_non_streaming_call_is_not_excused_by_the_streaming_gate():
    """A blocking call returns usage unconditionally. If it is absent there,
    the provider is the cause, and excusing it would hide the real fault."""
    reading = mg.check({"model": "gpt-4o"}, dialect=OPENAI)
    assert _state(reading, "stream_usage") == mg.NOT_APPLICABLE
    assert reading["all_open"] is True
    assert mg.why_absent(reading, "input")["explained"] is False


def test_an_integer_one_does_not_open_a_boolean_gate():
    """1 == True in Python. The flag is a boolean and a count is not a yes."""
    reading = mg.check({"stream": True, "stream_options": {"include_usage": 1}},
                       dialect=OPENAI)
    assert _state(reading, "stream_usage") == mg.SHUT


def test_the_flag_set_false_is_shut_and_not_merely_unset():
    reading = mg.check({"stream": True, "stream_options": {"include_usage": False}},
                       dialect=OPENAI)
    assert _state(reading, "stream_usage") == mg.SHUT


def test_the_responses_endpoint_carries_the_same_streaming_gate():
    reading = mg.check({"stream": True}, dialect=OPENAI_RESPONSES)
    assert _state(reading, "stream_usage") == mg.SHUT


def test_the_responses_include_list_opens_the_encrypted_reasoning_gate():
    reading = mg.check({"include": ["reasoning.encrypted_content"]},
                       dialect=OPENAI_RESPONSES)
    assert _state(reading, "encrypted_reasoning") == mg.OPEN
    shut = mg.check({"include": ["file_search_call.results"]},
                    dialect=OPENAI_RESPONSES)
    assert _state(shut, "encrypted_reasoning") == mg.SHUT


# --- the text gate versus the count gate ------------------------------------

def test_gemini_gates_the_thought_text_and_not_the_thought_token_count():
    """thoughtsTokenCount comes back either way. A call can therefore report
    reasoning tokens spent and no reasoning text, and both are correct."""
    reading = mg.check({"contents": []}, dialect=GEMINI)
    assert _state(reading, "include_thoughts") == mg.SHUT
    assert mg.why_absent(reading, mg.REASONING_TEXT)["explained"] is True
    assert mg.why_absent(reading, "reasoning")["explained"] is False


def test_gemini_include_thoughts_true_opens_the_text_gate():
    reading = mg.check(
        {"generationConfig": {"thinkingConfig": {"includeThoughts": True}}},
        dialect=GEMINI)
    assert _state(reading, "include_thoughts") == mg.OPEN


# --- three-state ------------------------------------------------------------

def test_an_omitted_ollama_think_is_unknown_and_never_read_as_false():
    """Omitting the key leaves the model default in charge. Calling that false
    would claim the caller suppressed reasoning when the caller said nothing."""
    reading = mg.check({"model": "qwen3:8b"}, dialect=OLLAMA)
    assert _state(reading, "think") == mg.UNKNOWN
    why = mg.why_absent(reading, mg.REASONING_TEXT)
    assert why["explained"] is False
    assert why["unknown"] == ["think"]


def test_an_explicit_ollama_think_false_explains_the_absence():
    reading = mg.check({"think": False}, dialect=OLLAMA)
    assert _state(reading, "think") == mg.SHUT
    assert mg.why_absent(reading, mg.REASONING_TEXT)["explained"] is True


def test_an_explicit_ollama_think_true_opens_the_gate():
    assert _state(mg.check({"think": True}, dialect=OLLAMA), "think") == mg.OPEN


# --- the serving stack ------------------------------------------------------

def test_a_server_we_were_told_nothing_about_is_unknown_not_shut():
    """Not being told how a server was started is not evidence it was started
    wrong, and reporting shut there would manufacture a fault."""
    reading = mg.check({}, dialect=OPENAI, kind="vllm")
    assert _state(reading, "reasoning_parser") == mg.UNKNOWN
    assert mg.why_absent(reading, mg.REASONING_TEXT)["explained"] is False


def test_a_vllm_launched_without_the_parser_flag_explains_the_missing_chain():
    """Without it the chain of thought stays inside message.content, so the
    answer silently contains the reasoning and no reasoning field exists."""
    reading = mg.check({}, dialect=OPENAI, kind="vllm",
                       server_argv=["vllm", "serve", "Qwen/Qwen3-8B",
                                    "--port", "8000"])
    assert _state(reading, "reasoning_parser") == mg.SHUT
    assert mg.why_absent(reading, mg.REASONING_TEXT)["by"] == ["reasoning_parser"]


def test_a_vllm_launched_with_the_parser_flag_is_open():
    reading = mg.check({}, dialect=OPENAI, kind="vllm",
                       server_argv=["vllm", "serve", "Qwen/Qwen3-8B",
                                    "--reasoning-parser", "qwen3"])
    assert _state(reading, "reasoning_parser") == mg.OPEN


def test_llama_server_reasoning_format_none_is_shut_though_the_flag_is_present():
    """Passing the flag is not enough. The value none leaves the chain inside
    content, which is the same outcome as never passing it."""
    shut = mg.check({}, dialect=OPENAI, kind="llamacpp",
                    server_argv=["llama-server", "--reasoning-format", "none"])
    assert _state(shut, "reasoning_format") == mg.SHUT
    joined = mg.check({}, dialect=OPENAI, kind="llamacpp",
                      server_argv=["llama-server", "--reasoning-format=none"])
    assert _state(joined, "reasoning_format") == mg.SHUT
    on = mg.check({}, dialect=OPENAI, kind="llamacpp",
                  server_argv=["llama-server", "--reasoning-format", "deepseek"])
    assert _state(on, "reasoning_format") == mg.OPEN


def test_a_flag_that_lost_its_value_is_shut_rather_than_open():
    for argv in (["vllm", "serve", "--reasoning-parser"],
                 ["vllm", "serve", "--reasoning-parser", "--port"]):
        reading = mg.check({}, dialect=OPENAI, kind="vllm", server_argv=argv)
        assert _state(reading, "reasoning_parser") == mg.SHUT


def test_a_kind_with_no_launch_gates_adds_none():
    reading = mg.check({}, dialect=OPENAI, kind="deepseek")
    assert [g["where"] for g in reading["gates"]] == ["request"]


# --- hostile and absent inputs ----------------------------------------------

def test_a_request_we_never_saw_is_unknown_throughout():
    """Unknown, not not_applicable: not seeing the body is a different claim
    from seeing a body that did not stream."""
    for junk in (None, [], "body", 7):
        reading = mg.check(junk, dialect=OPENAI)
        assert _state(reading, "stream_usage") == mg.UNKNOWN
        assert reading["all_open"] is False
        assert mg.why_absent(reading, "input")["unknown"] == ["stream_usage"]


def test_an_unmapped_dialect_has_no_gates_and_claims_nothing():
    reading = mg.check({"stream": True}, dialect="cohere")
    assert reading["gates"] == []
    assert mg.why_absent(reading, "input")["explained"] is False


def test_why_absent_on_a_non_reading_answers_unexplained():
    for junk in (None, [], "reading"):
        assert mg.why_absent(junk, "input")["explained"] is False


# --- a gate the service does not have ---------------------------------------

def _stream_gate(reading):
    return next(g for g in reading["gates"] if g["gate"] == "stream_usage")


def test_a_router_that_meters_usage_anyway_does_not_blame_the_request():
    """OpenRouter speaks the OpenAI schema and meters usage unconditionally, so
    a streamed call there is not excused by a flag its own docs call deprecated
    and without effect. Reporting shut hands an operator a cause that closes
    the question while the provider is the one that went silent."""
    reading = mg.check({"stream": True}, dialect=OPENAI, kind="openrouter")
    assert _state(reading, "stream_usage") == mg.NOT_APPLICABLE
    assert reading["all_open"] is True
    assert mg.why_absent(reading, "input")["explained"] is False


def test_the_waiver_names_the_kind_that_granted_it():
    gate = _stream_gate(mg.check({"stream": True}, dialect=OPENAI,
                                 kind="openrouter"))
    assert gate["waived_by_kind"] == "openrouter"
    assert "waived_on_kinds" not in gate


def test_an_unnamed_kind_keeps_the_default_and_carries_the_caveat():
    """Without a kind the dialect default is the only answer available, so it
    stands. What travels beside it is the set of kinds that would have waived
    the gate, which is the difference between a reading a stranger can check
    and one they have to take on faith."""
    gate = _stream_gate(mg.check({"stream": True}, dialect=OPENAI))
    assert gate["state"] == mg.SHUT
    assert gate["waived_on_kinds"] == ["openrouter"]


def test_a_kind_that_waives_nothing_carries_no_waiver_keys():
    gate = _stream_gate(mg.check({"stream": True}, dialect=OPENAI, kind="vllm"))
    assert gate["state"] == mg.SHUT
    assert "waived_by_kind" not in gate
    assert "waived_on_kinds" not in gate
