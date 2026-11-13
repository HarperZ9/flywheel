"""Falsifiers for the provider usage capture at the model boundary.

Hermetic: every input is a literal response dict, so no network and no provider
is touched. Load-bearing: (1) the verbatim block survives unaltered, so a wrong
normalization is always detectable from the same record; (2) a quantity the
provider did not report is ABSENT, never zero, because a cost layer that reads
absent as zero bills a silence; (3) the two cache conventions produce different
billable input from the same numbers, which is the arithmetic a naive summer
gets wrong; (4) a non-count value refuses by name instead of coercing;
(5) alternative spellings are tried in order and the winner is recorded, so the
four vendors riding the OpenAI schema each get their own cache figure read.
"""
import pytest

from harness import model_usage as mu


def _openai(usage, model="gpt-4o-2024-08-06"):
    return {"model": model, "choices": [{"message": {"content": "hi"}}],
            "usage": usage}


def _anthropic(usage, model="claude-sonnet-4"):
    return {"model": model, "content": [{"type": "text", "text": "hi"}],
            "usage": usage}


def _gemini(meta, model="gemini-2.5-flash-002"):
    return {"modelVersion": model,
            "candidates": [{"content": {"parts": [{"text": "hi"}]}}],
            "usageMetadata": meta}


# --- verbatim ---------------------------------------------------------------

def test_reported_block_is_the_providers_own_object():
    usage = {"prompt_tokens": 100, "completion_tokens": 50,
             "total_tokens": 150, "vendor_extension": {"anything": True}}
    block = mu.reported_block(_openai(usage), dialect=mu.OPENAI)
    assert block == usage


def test_reported_block_is_a_copy_not_the_response_object():
    """A holder of the record must not be able to mutate the response it came
    from, and a later reader of the response must not see edits made downstream."""
    response = _openai({"prompt_tokens": 1})
    block = mu.reported_block(response, dialect=mu.OPENAI)
    block["prompt_tokens"] = 999
    assert response["usage"]["prompt_tokens"] == 1


def test_absent_usage_object_reports_absent_provenance():
    record = mu.capture({"model": "m", "choices": []}, dialect=mu.OPENAI)
    assert record["provenance"] == "absent"
    assert record["reported"] is None
    assert "counts" not in record


# --- never fill -------------------------------------------------------------

def test_unreported_quantity_is_absent_and_not_zero():
    record = mu.capture(_openai({"prompt_tokens": 100, "completion_tokens": 50}),
                        dialect=mu.OPENAI)
    assert record["counts"] == {"input": 100, "output": 50}
    assert "cache_read" not in record["counts"]
    assert "reasoning" not in record["counts"]


def test_reported_zero_is_kept_as_a_measurement():
    """Absent and zero are different claims, and both have to survive."""
    record = mu.capture(
        _openai({"prompt_tokens": 100, "completion_tokens": 0,
                 "prompt_tokens_details": {"cached_tokens": 0}}),
        dialect=mu.OPENAI)
    assert record["counts"]["output"] == 0
    assert record["counts"]["cache_read"] == 0


# --- the cache convention ---------------------------------------------------

def test_same_numbers_bill_differently_under_the_two_conventions():
    """OpenAI counts cached tokens inside the prompt figure; Anthropic counts
    them beside it. Identical integers therefore mean different spend."""
    openai = mu.capture(
        _openai({"prompt_tokens": 100, "completion_tokens": 50,
                 "prompt_tokens_details": {"cached_tokens": 40}}),
        dialect=mu.OPENAI)
    anthropic = mu.capture(
        _anthropic({"input_tokens": 100, "output_tokens": 50,
                    "cache_read_input_tokens": 40}),
        dialect=mu.ANTHROPIC)
    assert openai["counts"]["input"] == anthropic["counts"]["input"] == 100
    assert openai["counts"]["cache_read"] == anthropic["counts"]["cache_read"] == 40
    assert mu.billable_input(openai) == 60
    assert mu.billable_input(anthropic) == 100


def test_billable_input_refuses_when_the_cached_operand_is_missing():
    record = mu.capture(_openai({"prompt_tokens": 100}), dialect=mu.OPENAI)
    assert mu.billable_input(record) is None


def test_billable_input_never_goes_negative():
    record = mu.capture(
        _openai({"prompt_tokens": 10,
                 "prompt_tokens_details": {"cached_tokens": 40}}),
        dialect=mu.OPENAI)
    assert mu.billable_input(record) == 0


# --- the reasoning convention -----------------------------------------------

def test_reasoning_sits_inside_output_on_openai_and_outside_it_on_gemini():
    """Gemini documents totalTokenCount as prompt + thoughts + candidates, so
    its thought tokens are NOT part of the candidates figure. OpenAI states the
    opposite for reasoning_tokens. Subtracting on both is wrong once."""
    openai = mu.capture(
        _openai({"prompt_tokens": 10, "completion_tokens": 50,
                 "completion_tokens_details": {"reasoning_tokens": 30}}),
        dialect=mu.OPENAI)
    gemini = mu.capture(
        _gemini({"promptTokenCount": 10, "candidatesTokenCount": 50,
                 "thoughtsTokenCount": 30, "totalTokenCount": 90}),
        dialect=mu.GEMINI)
    assert mu.billable_output(openai) == 20
    assert mu.billable_output(gemini) == 50


def test_billable_output_refuses_on_an_unknown_convention():
    """ollama documents no thinking-token figure, so its convention is unknown
    and unknown must not be answered as if it were False."""
    record = mu.capture({"model": "q", "prompt_eval_count": 5, "eval_count": 7},
                        dialect=mu.OLLAMA)
    assert record["output_includes_reasoning"] is None
    assert mu.billable_output(record) is None


def test_anthropic_thinking_tokens_are_read_from_the_details_object():
    record = mu.capture(
        _anthropic({"input_tokens": 10, "output_tokens": 50,
                    "output_tokens_details": {"thinking_tokens": 30}}),
        dialect=mu.ANTHROPIC)
    assert record["counts"]["reasoning"] == 30
    assert mu.billable_output(record) == 20


# --- alternative spellings --------------------------------------------------

def test_deepseeks_own_cache_key_answers_when_the_details_object_is_absent():
    record = mu.capture(
        _openai({"prompt_tokens": 100, "completion_tokens": 5,
                 "prompt_cache_hit_tokens": 40, "prompt_cache_miss_tokens": 60}),
        dialect=mu.OPENAI)
    assert record["counts"]["cache_read"] == 40
    assert record["read_from"]["cache_read"] == "prompt_cache_hit_tokens"


def test_the_standard_spelling_wins_when_both_are_present():
    record = mu.capture(
        _openai({"prompt_tokens": 100,
                 "prompt_tokens_details": {"cached_tokens": 7},
                 "prompt_cache_hit_tokens": 40}),
        dialect=mu.OPENAI)
    assert record["counts"]["cache_read"] == 7
    assert record["read_from"]["cache_read"] == "prompt_tokens_details.cached_tokens"


def test_vllm_cache_write_spelling_is_read():
    record = mu.capture(
        _openai({"prompt_tokens": 100,
                 "prompt_tokens_details": {"created_cache_tokens": 12}}),
        dialect=mu.OPENAI)
    assert record["counts"]["cache_write"] == 12


# --- named refusals ---------------------------------------------------------

@pytest.mark.parametrize("bad", [1.5, "100", [], {"n": 1}])
def test_a_non_integer_count_refuses_by_name(bad):
    record = mu.capture(_openai({"prompt_tokens": bad}), dialect=mu.OPENAI)
    assert record["refused"] == mu.NOT_COUNTS
    assert "counts" not in record
    assert record["reported"] == {"prompt_tokens": bad}


def test_a_boolean_is_not_a_token_count():
    """bool is a subclass of int, so an isinstance check would accept True as
    a count of one. The type identity check is what rejects it."""
    record = mu.capture(_openai({"prompt_tokens": True}), dialect=mu.OPENAI)
    assert record["refused"] == mu.NOT_COUNTS


def test_a_negative_count_refuses():
    record = mu.capture(_openai({"prompt_tokens": -1}), dialect=mu.OPENAI)
    assert record["refused"] == mu.NOT_COUNTS


def test_an_unmapped_dialect_refuses_rather_than_borrowing_another_map():
    record = mu.capture(_openai({"prompt_tokens": 100}), dialect="cohere")
    assert record["refused"] == mu.UNMAPPED
    assert "counts" not in record


def test_normalized_returns_counts_or_refused_and_never_both():
    for dialect in mu.DIALECTS:
        reading = mu.normalized({}, dialect=dialect)
        assert ("counts" in reading) != ("refused" in reading)
    assert "refused" in mu.normalized(None, dialect=mu.OPENAI)


# --- served model -----------------------------------------------------------

def test_served_model_is_read_from_each_dialects_own_key():
    assert mu.served_model(_openai({}), dialect=mu.OPENAI) == "gpt-4o-2024-08-06"
    assert mu.served_model(_anthropic({}), dialect=mu.ANTHROPIC) == "claude-sonnet-4"
    assert mu.served_model(_gemini({}), dialect=mu.GEMINI) == "gemini-2.5-flash-002"


def test_a_pinned_revision_answering_an_alias_reads_as_a_difference():
    """Not a fault. The receipt carries what the server said it served."""
    record = mu.capture(_gemini({}), dialect=mu.GEMINI,
                        requested_model="gemini-2.5-flash")
    assert record["served_matches_requested"] is False
    assert record["served_model"] == "gemini-2.5-flash-002"


def test_a_missing_operand_makes_the_comparison_unanswered_not_false():
    record = mu.capture({"choices": []}, dialect=mu.OPENAI, requested_model="x")
    assert record["served_matches_requested"] is None


# --- ollama -----------------------------------------------------------------

def test_ollama_counts_come_off_the_response_itself():
    record = mu.capture(
        {"model": "qwen3:8b", "prompt_eval_count": 100, "eval_count": 50,
         "prompt_eval_cached_count": 40, "total_duration": 1},
        dialect=mu.OLLAMA)
    assert record["counts"] == {"input": 100, "output": 50, "cache_read": 40}
    assert mu.billable_input(record) == 60


# --- pricing handoff --------------------------------------------------------

def test_priceable_reports_each_quantity_or_none_and_never_zero_fills():
    record = mu.capture(
        _anthropic({"input_tokens": 100, "output_tokens": 50,
                    "cache_read_input_tokens": 40}),
        dialect=mu.ANTHROPIC)
    priced = mu.priceable(record)
    assert priced["uncached_input"] == 100
    assert priced["cache_read"] == 40
    assert priced["output"] == 50
    assert priced["cache_write"] is None


def test_priceable_carries_the_refusal_reason_when_there_is_no_reading():
    record = mu.capture(_openai({"prompt_tokens": "100"}), dialect=mu.OPENAI)
    priced = mu.priceable(record)
    assert priced["priceable"] is False
    assert priced["reason"] == mu.NOT_COUNTS
