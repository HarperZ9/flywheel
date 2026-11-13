"""Falsifiers for five readings a single-path dialect table gets wrong.

Each test here pins a case where the naive map produces a plausible number
rather than an error, which is the only kind of mistake this layer cannot catch
after the fact. Load-bearing: (1) a proxied ollama call names the model that
actually ran and not the local alias it was addressed by; (2) Anthropic's two
cache-write TTL buckets are captured without being added to the total they
already sum to; (3) a Responses body read with the chat map reports every count
absent, which is why the endpoint gets its own dialect; (4) a cost the provider
measured is read as a cost and never through the whole-count check; (5) on
ollama an absent count does not mean the same thing it means everywhere else.
"""
from harness import model_reasoning as mr
from harness import model_usage as mu
from harness.model_dialects import (ANTHROPIC, DIALECTS, OLLAMA, OPENAI,
                                    OPENAI_RESPONSES)

CHAIN = "the summarized chain"


# --- 1. the model that actually ran -----------------------------------------

def test_a_proxied_ollama_call_names_the_remote_model_not_the_local_alias():
    """ollama fills remote_model when it forwarded the call to a cloud host. Its
    own model field then holds the local alias, so reading that names the thing
    the request was addressed to rather than the thing that answered."""
    response = {"model": "gpt-oss:120b-cloud", "remote_model": "gpt-oss:120b",
                "prompt_eval_count": 10, "eval_count": 5}
    assert mu.served_model(response, dialect=OLLAMA) == "gpt-oss:120b"


def test_a_local_ollama_call_still_names_its_own_model():
    response = {"model": "qwen3:8b", "prompt_eval_count": 10, "eval_count": 5}
    assert mu.served_model(response, dialect=OLLAMA) == "qwen3:8b"


def test_an_empty_remote_model_falls_through_to_the_local_name():
    """An empty string is not a name, and stopping at it would report no served
    model for a call that plainly had one."""
    response = {"model": "qwen3:8b", "remote_model": ""}
    assert mu.served_model(response, dialect=OLLAMA) == "qwen3:8b"


# --- 2. the cache-write buckets ---------------------------------------------

def _anthropic_ttl():
    return {"model": "claude-sonnet-4", "content": [],
            "usage": {"input_tokens": 100, "output_tokens": 50,
                      "cache_creation_input_tokens": 1000,
                      "cache_creation": {"ephemeral_5m_input_tokens": 400,
                                         "ephemeral_1h_input_tokens": 600}}}


def test_the_ttl_buckets_are_captured_beside_the_total_they_sum_to():
    record = mu.capture(_anthropic_ttl(), dialect=ANTHROPIC)
    counts = record["counts"]
    assert counts["cache_write"] == 1000
    assert counts["cache_write_5m"] == 400
    assert counts["cache_write_1h"] == 600
    assert counts["cache_write_5m"] + counts["cache_write_1h"] == counts["cache_write"]


def test_the_price_handoff_nests_the_buckets_so_they_cannot_be_added_twice():
    """A one-hour write costs more per token than a five-minute one, so the
    split has to survive. Flat beside the total it would be summed with it, and
    the call would bill two thousand tokens for a thousand."""
    priced = mu.priceable(mu.capture(_anthropic_ttl(), dialect=ANTHROPIC))
    assert priced["cache_write"] == 1000
    assert priced["cache_write_ttl"] == {"5m": 400, "1h": 600}


def test_a_provider_reporting_only_the_total_leaves_the_buckets_absent():
    record = mu.capture(
        {"usage": {"input_tokens": 1, "cache_creation_input_tokens": 700}},
        dialect=ANTHROPIC)
    assert record["counts"]["cache_write"] == 700
    assert "cache_write_5m" not in record["counts"]
    priced = mu.priceable(record)
    assert priced["cache_write_ttl"] == {"5m": None, "1h": None}


# --- 3. one vendor, two endpoints -------------------------------------------

def _responses_body():
    return {"model": "o4-mini-2025-04-16", "output": [],
            "usage": {"input_tokens": 100, "output_tokens": 50,
                      "total_tokens": 150,
                      "input_tokens_details": {"cached_tokens": 40},
                      "output_tokens_details": {"reasoning_tokens": 30}}}


def test_the_chat_map_reads_a_responses_body_as_a_total_with_no_parts():
    """The failure this dialect exists to prevent, and it is worse than a blank
    reading. total_tokens is spelled the same on both endpoints, so the chat map
    finds the total and misses every part of it. Nothing raises, the block is
    present and verbatim, and the record says a hundred and fifty tokens were
    spent on no input and no output."""
    record = mu.capture(_responses_body(), dialect=OPENAI)
    assert record["provenance"] == "provider_reported"
    assert record["counts"] == {"total": 150}
    assert mu.billable_input(record) is None
    assert mu.billable_output(record) is None


def test_the_responses_dialect_reads_the_same_body_completely():
    record = mu.capture(_responses_body(), dialect=OPENAI_RESPONSES,
                        requested_model="o4-mini")
    assert record["counts"] == {"input": 100, "output": 50, "total": 150,
                                "cache_read": 40, "reasoning": 30}
    assert record["read_from"]["cache_read"] == "input_tokens_details.cached_tokens"
    assert record["served_matches_requested"] is False
    assert mu.billable_input(record) == 60
    assert mu.billable_output(record) == 20


def test_the_responses_dialect_is_listed_so_a_caller_can_enumerate_it():
    assert OPENAI_RESPONSES in DIALECTS
    assert OPENAI_RESPONSES != OPENAI


def test_responses_reasoning_summaries_are_read_and_the_ciphertext_is_not():
    """The summary is less than a thinking block gives, and the real chain
    arrives encrypted. Digesting the ciphertext would put a character count on
    something that is not text."""
    record = mr.capture(
        {"output": [{"type": "reasoning",
                     "summary": [{"type": "summary_text", "text": CHAIN}],
                     "encrypted_content": "ENCRYPTEDBLOB"},
                    {"type": "message",
                     "content": [{"type": "output_text", "text": "the answer"}]}]},
        dialect=OPENAI_RESPONSES)
    assert record["text"] == CHAIN
    assert record["source_key"] == "summary_text"
    assert record["encrypted_blocks"] == 1
    assert "ENCRYPTEDBLOB" not in repr(record)
    assert "the answer" not in record["text"]


def test_an_encrypted_only_reasoning_item_is_counted_and_reports_no_text():
    record = mr.capture(
        {"output": [{"type": "reasoning", "summary": [],
                     "encrypted_content": "BLOB"}]},
        dialect=OPENAI_RESPONSES)
    assert record["present"] is False
    assert record["encrypted_blocks"] == 1
    assert record["dialect_unmapped"] is False


# --- 4. a cost the provider measured ----------------------------------------

def _openrouter():
    return {"model": "deepseek/deepseek-chat", "choices": [],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50,
                      "cost": 0.00042, "is_byok": False,
                      "cost_details": {"upstream_inference_cost": 0.00031,
                                       "server_tool_cost": 0.0}}}


def test_a_provider_reported_cost_is_read_with_the_path_it_came_from():
    """Measured by the party doing the billing, so it outranks the same call
    priced locally, and the two disagreeing is the useful signal."""
    record = mu.capture(_openrouter(), dialect=OPENAI)
    cost = record["cost"]
    assert cost["present"] is True
    assert cost["values"]["cost"] == 0.00042
    assert cost["values"]["upstream_inference_cost"] == 0.00031
    assert cost["values"]["server_tool_cost"] == 0.0
    assert cost["read_from"]["cost"] == "usage.cost"
    assert cost["byok"] is False


def test_a_float_cost_does_not_refuse_the_token_counts_beside_it():
    """The cost shares the usage block with the counts. Running it through the
    whole-count check would refuse the entire reading over a legal value."""
    record = mu.capture(_openrouter(), dialect=OPENAI)
    assert record["counts"] == {"input": 100, "output": 50}
    assert "refused" not in record


def test_the_price_handoff_carries_the_measured_cost_when_there_is_one():
    priced = mu.priceable(mu.capture(_openrouter(), dialect=OPENAI))
    assert priced["provider_reported"]["values"]["cost"] == 0.00042


def test_a_provider_that_reports_no_cost_says_absent_rather_than_zero():
    record = mu.capture({"model": "gpt-4o", "usage": {"prompt_tokens": 1}},
                        dialect=OPENAI)
    assert record["cost"]["present"] is False
    assert record["cost"]["values"] == {}
    assert record["cost"]["byok"] is None
    assert "provider_reported" not in mu.priceable(record)


def test_a_cost_that_is_not_an_amount_is_skipped_rather_than_read():
    for bad in ("0.004", True, -1, None, {"usd": 1}):
        record = mu.capture(
            {"usage": {"prompt_tokens": 1, "cost": bad}}, dialect=OPENAI)
        assert record["cost"]["present"] is False
        assert record["counts"] == {"input": 1}


def test_a_byok_call_says_so_because_it_changes_what_the_cost_means():
    record = mu.capture(
        {"usage": {"prompt_tokens": 1, "cost": 0.0, "is_byok": True}},
        dialect=OPENAI)
    assert record["cost"]["byok"] is True
    assert record["cost"]["values"]["cost"] == 0.0


def test_the_dialects_that_report_no_cost_read_no_cost():
    for dialect in (ANTHROPIC, OLLAMA, OPENAI_RESPONSES):
        reading = mu.reported_cost({"usage": {"cost": 9.99}}, dialect=dialect)
        assert reading["present"] is False


# --- 5. what an absent count means ------------------------------------------

def test_absent_means_unreported_everywhere_except_ollama():
    """ollama tags every metrics field omitempty, so a real zero is dropped
    from the JSON and arrives looking exactly like a field never filled in."""
    record = mu.capture({"model": "q", "prompt_eval_count": 5, "eval_count": 7},
                        dialect=OLLAMA)
    assert record["absent_means_unreported"] is False
    assert "cache_read" not in record["counts"]
    for dialect in (OPENAI, OPENAI_RESPONSES, ANTHROPIC):
        other = mu.capture({"usage": {}}, dialect=dialect)
        assert other["absent_means_unreported"] is True


def test_an_unmapped_dialect_makes_the_absent_meaning_unknown_too():
    record = mu.capture({"usage": {}}, dialect="cohere")
    assert record["absent_means_unreported"] is None


# --- 6. the model a router actually reached ---------------------------------

def _routed():
    return {"model": "deepseek/deepseek-chat",
            "choices": [{"message": {"role": "assistant", "content": "hi",
                                     "model": "deepseek/deepseek-chat-v3-0324"}}],
            "usage": {"prompt_tokens": 1}}


def test_a_routed_call_names_the_model_that_generated_not_the_route():
    """Top-level model is the route the request addressed. A proxy documents
    choices[].message.model as the model that generated the message, and on a
    router the two disagreeing is the ordinary case."""
    assert mu.served_model(_routed(), dialect=OPENAI) == (
        "deepseek/deepseek-chat-v3-0324")


def test_a_direct_vendor_call_still_reads_the_top_level_model():
    response = {"model": "gpt-4o", "choices": [{"message": {"content": "hi"}}]}
    assert mu.served_model(response, dialect=OPENAI) == "gpt-4o"


def test_an_empty_choices_array_falls_through_rather_than_raising():
    assert mu.served_model({"model": "gpt-4o", "choices": []},
                           dialect=OPENAI) == "gpt-4o"


def test_a_choices_field_of_the_wrong_shape_does_not_break_the_walk():
    for junk in ({"model": "gpt-4o", "choices": {"0": {"message": {"model": "x"}}}},
                 {"model": "gpt-4o", "choices": "none"},
                 {"model": "gpt-4o", "choices": [{"message": "none"}]},
                 {"model": "gpt-4o", "choices": [None]}):
        assert mu.served_model(junk, dialect=OPENAI) == "gpt-4o"


def test_the_route_and_the_generator_disagreeing_is_visible_to_the_caller():
    """A receipt that reports the route as the served model says a call ran on
    something it did not, and every figure beside it inherits that claim."""
    record = mu.capture(_routed(), dialect=OPENAI,
                        requested_model="deepseek/deepseek-chat")
    assert record["served_model"] == "deepseek/deepseek-chat-v3-0324"
    assert record["served_matches_requested"] is False
