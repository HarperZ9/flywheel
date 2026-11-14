"""Virtual-key budgets through the real gateway: debits and refusals.

A real gateway on a loopback port, a stub upstream that replays recorded
replies with known token counts, and keys in the in-memory store. The counts
are the provider's: openai/turn2 reports 451 prompt and 9 completion tokens;
upstream/anthropic_cached reports 12 input, 11 output, 2051 cache read and 300
cache write; upstream/openai_cached reports 451 prompt of which 400 cached, and
9 completion.

Error shapes, read 2026-11-14: see tests.gateway_keys_support.
"""
import pytest

from harness import gateway_keys
from tests import gateway_messages_support as support
from tests.gateway_keys_support import (  # noqa: F401  (fixtures)
    BODIES, TURN2_TOKENS, keyed, post, served, stream_bytes, turn2)

PATHS = ["/v1/messages", "/v1/responses"]


@pytest.mark.parametrize("path", PATHS)
def test_one_call_then_three_debit_the_provider_counts_exactly(keyed, served, path):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream, ledger = served(turn2(3))
    assert post(url, path, raw)[0] == 200
    assert keys.row("ci-bot")["totals"] == {
        "calls": 1, "tokens": 460, "input_tokens": 451, "output_tokens": 9,
        "cache_read_tokens": 0, "cache_write_tokens": 0,
        "estimated_calls": 0, "estimated_tokens": 0}
    assert post(url, path, raw)[0] == 200 and post(url, path, raw, header="Authorization")[0] == 200
    totals = keys.row("ci-bot")["totals"]
    assert (totals["calls"], totals["tokens"]) == (3, 3 * TURN2_TOKENS)
    assert (totals["input_tokens"], totals["output_tokens"]) == (1353, 27)
    assert len(upstream.requests) == 3
    assert [entry.meta["charged_tokens"] for entry in ledger.entries] == [460, 460, 460]


@pytest.mark.parametrize("path", PATHS)
def test_a_streamed_call_debits_when_the_stream_finishes(keyed, served, path):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, _upstream, ledger = served([support.stream_answer(stream_bytes("openai", "turn2"))])
    status, headers, body = post(url, path, raw, {**BODIES[path], "stream": True})
    assert status == 200 and headers["Content-Type"] == "text/event-stream"
    last = b"event: message_stop" if path == "/v1/messages" else b"event: response.completed"
    assert last in body                             # the stream ran to its documented end
    totals = keys.row("ci-bot")["totals"]
    assert (totals["calls"], totals["tokens"], totals["input_tokens"], totals["output_tokens"]) == (
        1, 460, 451, 9)
    assert ledger.entries[0].meta["key"] == "ci-bot" and len(ledger.entries) == 1


@pytest.mark.parametrize("path", PATHS)
def test_cache_tokens_are_each_counted_once_and_priced_as_input(keyed, served, path):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot", price_in=3.0, price_out=15.0)
    url, _upstream, _ledger = served(
        [support.json_answer(support.load("upstream/anthropic_cached.json"))], "anthropic")
    assert post(url, path, raw)[0] == 200
    row = keys.row("ci-bot")
    assert row["totals"]["tokens"] == 12 + 11 + 2051 + 300 == 2374
    assert (row["totals"]["input_tokens"], row["totals"]["output_tokens"],
            row["totals"]["cache_read_tokens"], row["totals"]["cache_write_tokens"]) == (
        12, 11, 2051, 300)
    # (12 + 2051 + 300) at $3 per million, 11 at $15 per million
    assert gateway_keys.spend(row) == 0.007254


def test_an_openai_cached_count_is_not_added_twice(keyed, served):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, _upstream, _ledger = served(
        [support.json_answer(support.load("upstream/openai_cached.json"))])
    assert post(url, "/v1/messages", raw)[0] == 200
    totals = keys.row("ci-bot")["totals"]
    assert (totals["input_tokens"], totals["cache_read_tokens"], totals["output_tokens"]) == (
        51, 400, 9)
    assert totals["tokens"] == 460                  # the provider's 451 + 9, not 451 + 400 + 9


def _crossing(keyed, served, path, **limits):
    """Two calls with a key whose first call crosses its limit."""
    keys, _store = keyed
    raw, _ = keys.create("ci-bot", **limits)
    url, upstream, ledger = served(turn2(2))
    first = post(url, path, raw)
    second = post(url, path, raw)
    return first, second, upstream, ledger, keys


def test_messages_refuses_the_call_after_the_crossing_before_any_upstream_call(keyed, served):
    first, second, upstream, ledger, keys = _crossing(keyed, served, "/v1/messages",
                                                      token_limit=460)
    status, headers, body = second
    assert first[0] == 200 and len(upstream.requests) == 1      # the stub saw no second request
    assert status == 400 and headers["x-should-retry"] == "false"
    assert body == {"type": "error", "request_id": headers["request-id"], "error": {
        "type": "invalid_request_error",
        "message": "gateway key 'ci-bot' has reached its token limit (460 of 460 tokens used); "
                   "zero its counters with `flywheel gateway-key reset ci-bot` or create a key "
                   "with a higher limit. Nothing was sent upstream."}}
    assert support.kinds(ledger) == ["endpoint_call", "endpoint_call_refused"]
    refused = ledger.entries[1]
    assert refused.content == "token_limit" and refused.meta == {
        "interface": "anthropic-messages", "key": "ci-bot", "reason": "token_limit",
        "key_fp": keys.row("ci-bot")["fingerprint"]}
    assert keys.row("ci-bot")["totals"]["calls"] == 1           # a refusal is not a debit


def test_responses_refuses_the_call_after_the_crossing_before_any_upstream_call(keyed, served):
    first, second, upstream, ledger, _keys = _crossing(keyed, served, "/v1/responses",
                                                       token_limit=100)
    status, headers, body = second
    assert first[0] == 200 and len(upstream.requests) == 1
    assert status == 429 and headers["x-should-retry"] == "false"
    assert set(body) == {"error"} and set(body["error"]) == {"message", "type", "param", "code"}
    assert (body["error"]["type"], body["error"]["code"], body["error"]["param"]) == (
        "insufficient_quota", "key_budget_exceeded", None)
    assert "gateway key 'ci-bot' has reached its token limit (460 of 100 tokens used)" in (
        body["error"]["message"])
    assert support.kinds(ledger) == ["endpoint_call", "endpoint_call_refused"]
    assert ledger.entries[1].meta["interface"] == "openai-responses"


@pytest.mark.parametrize("path", PATHS)
def test_control_without_the_limit_check_the_second_call_reaches_upstream(
        keyed, served, monkeypatch, path):
    """The refusal tests assert one upstream request. With the check removed the
    same two calls give two, so that assertion fails when a key over budget is served."""
    monkeypatch.setattr(gateway_keys, "over", lambda row: None)
    first, second, upstream, ledger, keys = _crossing(keyed, served, path, token_limit=460)
    assert (first[0], second[0]) == (200, 200)
    assert len(upstream.requests) == 2
    assert support.kinds(ledger) == ["endpoint_call", "endpoint_call"]
    assert keys.row("ci-bot")["totals"]["tokens"] == 920


@pytest.mark.parametrize("path, status", [("/v1/messages", 400), ("/v1/responses", 429)])
def test_a_spend_limit_is_enforced_from_the_keys_own_prices(keyed, served, path, status):
    # one call costs 451 * $2 + 9 * $10 per million = $0.000992; the limit is $0.0009
    first, second, upstream, ledger, keys = _crossing(
        keyed, served, path, spend_limit=0.0009, price_in=2.0, price_out=10.0)
    assert first[0] == 200 and second[0] == status and len(upstream.requests) == 1
    assert gateway_keys.spend(keys.row("ci-bot")) == 0.000992
    said = second[2]["error"]["message"]
    assert "gateway key 'ci-bot' has reached its spend limit ($0.000992 of $0.000900 spent)" in said
    assert ledger.entries[1].meta["reason"] == "spend_limit"


def test_a_key_under_its_limit_keeps_working_and_reset_reopens_one_over_it(keyed, served):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot", token_limit=461)
    url, upstream, _ledger = served(turn2(3))
    assert post(url, "/v1/messages", raw)[0] == 200             # 460 of 461: still under
    assert post(url, "/v1/messages", raw)[0] == 200             # 920: this call crossed it
    assert post(url, "/v1/messages", raw)[0] == 400
    keys.reset("ci-bot")
    assert post(url, "/v1/messages", raw)[0] == 200 and len(upstream.requests) == 3


def test_a_failed_upstream_call_names_the_key_and_is_not_charged(keyed, served):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, _upstream, ledger = served(
        [support.json_answer(support.load("upstream/openai_rate_limited.json"), 429)])
    assert post(url, "/v1/messages", raw)[0] == 429
    assert support.kinds(ledger) == ["endpoint_call_failed"]
    assert ledger.entries[0].meta["key"] == "ci-bot"
    assert ledger.entries[0].meta["key_fp"] == keys.row("ci-bot")["fingerprint"]
    assert keys.row("ci-bot")["totals"]["calls"] == 0


def test_token_counting_checks_the_key_and_charges_nothing(keyed, served):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot", token_limit=5)
    url, upstream, ledger = served(
        [support.json_answer(support.load("upstream/anthropic_count.json"))], "anthropic")
    body = {"model": "claude-sonnet-5", "messages": [{"role": "user", "content": "Hi"}]}
    assert post(url, "/v1/messages/count_tokens", raw, body)[0] == 200
    assert keys.row("ci-bot")["totals"]["calls"] == 0 and ledger.entries == []
    keys.debit("ci-bot", {"input": 5})
    assert post(url, "/v1/messages/count_tokens", raw, body)[0] == 400
    assert len(upstream.requests) == 1
