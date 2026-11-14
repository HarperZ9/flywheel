"""Official SDK clients holding a virtual key, and what the SDK models allow for usage.

The `anthropic` and `openai` Python SDKs are pointed at a real gateway on a
loopback port, with a virtual key from the in-memory store as the API key.
The gateway talks to a stub upstream; no provider is called. Both SDKs are
test-only imports: a test is skipped where its SDK is not installed.

Read 2026-11-14 in the installed packages:
  anthropic 0.95.0  types/usage.py: `input_tokens: int`, `output_tokens: int`
      (required), the two cache counts `Optional[int]`; `_exceptions.py`:
      400 BadRequestError, 401 AuthenticationError, 403 PermissionDeniedError
  openai 2.36.0     types/responses/response.py: `usage: Optional[ResponseUsage]`;
      types/responses/response_usage.py: every count a required int;
      `_exceptions.py`: 429 RateLimitError, 401 AuthenticationError,
      403 PermissionDeniedError
"""
import pytest

from tests.gateway_keys_support import (  # noqa: F401  (fixtures)
    keyed, no_usage, served, turn2)

TEXT = "Wrote n.txt.\nNothing else changed."


def _anthropic(url, key, **how):
    sdk = pytest.importorskip("anthropic")
    credential = how or {"api_key": key}
    return sdk, sdk.Anthropic(base_url=url, max_retries=0, timeout=30, **credential)


def _openai(url, key, retries=0):
    sdk = pytest.importorskip("openai")
    return sdk, sdk.OpenAI(base_url=f"{url}/v1", api_key=key, max_retries=retries, timeout=30)


def _message(client, model="claude-sonnet-5"):
    return client.messages.create(model=model, max_tokens=64,
                                  messages=[{"role": "user", "content": "What changed?"}])


@pytest.mark.parametrize("how", ["api_key", "auth_token"])
def test_the_anthropic_sdk_works_with_a_virtual_key_in_either_header(keyed, served, how):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, _upstream, ledger = served(turn2(1))
    _sdk, client = _anthropic(url, raw, **{how: raw})
    message = _message(client)
    assert message.content[0].text == TEXT
    assert (message.usage.input_tokens, message.usage.output_tokens) == (451, 9)
    assert ledger.entries[0].meta["key"] == "ci-bot"
    assert keys.row("ci-bot")["totals"]["tokens"] == 460


def test_the_anthropic_sdk_raises_its_typed_errors_for_a_key(keyed, served):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot", token_limit=460, models=["claude-sonnet-5"])
    url, upstream, _ledger = served(turn2(1))
    sdk, client = _anthropic(url, raw)
    with pytest.raises(sdk.PermissionDeniedError) as denied:
        _message(client, model="claude-opus-5")
    assert denied.value.body["error"]["type"] == "permission_error"
    assert _message(client).stop_reason == "end_turn"           # this call crosses the limit
    with pytest.raises(sdk.BadRequestError) as refused:
        _message(client)
    assert refused.value.status_code == 400
    assert refused.value.body["error"]["type"] == "invalid_request_error"
    assert "gateway key 'ci-bot' has reached its token limit" in str(refused.value)
    keys.revoke("ci-bot")
    with pytest.raises(sdk.AuthenticationError):
        _message(client)
    assert len(upstream.requests) == 1


def test_the_openai_sdk_works_with_a_virtual_key(keyed, served):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, _upstream, ledger = served(turn2(1))
    _sdk, client = _openai(url, raw)
    response = client.responses.create(model="gpt-5.3-codex", input="What changed?")
    assert response.output_text == TEXT and response.usage.total_tokens == 460
    assert ledger.entries[0].meta["key"] == "ci-bot"
    assert keys.row("ci-bot")["totals"]["tokens"] == 460


def test_the_openai_sdk_raises_its_typed_errors_for_a_key(keyed, served):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot", token_limit=460, models=["gpt-5.3-codex"])
    url, upstream, _ledger = served(turn2(1))
    sdk, client = _openai(url, raw)
    with pytest.raises(sdk.PermissionDeniedError) as denied:
        client.responses.create(model="gpt-5.5", input="What changed?")
    assert denied.value.code == "model_not_allowed" and denied.value.param == "model"
    assert client.responses.create(model="gpt-5.3-codex", input="What changed?").status == (
        "completed")
    with pytest.raises(sdk.RateLimitError) as refused:
        client.responses.create(model="gpt-5.3-codex", input="What changed?")
    assert (refused.value.status_code, refused.value.type, refused.value.code) == (
        429, "insufficient_quota", "key_budget_exceeded")
    keys.revoke("ci-bot")
    with pytest.raises(sdk.AuthenticationError):
        client.responses.create(model="gpt-5.3-codex", input="What changed?")
    assert len(upstream.requests) == 1


def test_a_budget_refusal_is_not_retried_by_an_sdk_with_retries_on(keyed, served):
    """429 is a status the SDK retries. `x-should-retry: false` stops it: the
    gateway sees one refused request, not three."""
    keys, _store = keyed
    raw, _ = keys.create("ci-bot", token_limit=1)
    keys.debit("ci-bot", {"input": 1})
    url, upstream, ledger = served([])
    sdk, client = _openai(url, raw, retries=2)
    with pytest.raises(sdk.RateLimitError):
        client.responses.create(model="gpt-5.3-codex", input="What changed?")
    assert [entry.kind for entry in ledger.entries] == ["endpoint_call_refused"]
    assert upstream.requests == []


def test_the_anthropic_model_needs_integer_counts_so_messages_sends_zeros(keyed, served):
    """What the SDK model says: null input_tokens fails validation, 0 passes."""
    sdk = pytest.importorskip("anthropic")
    pydantic = pytest.importorskip("pydantic")
    with pytest.raises(pydantic.ValidationError):
        sdk.types.Usage.model_validate({"input_tokens": None, "output_tokens": None})
    assert sdk.types.Usage.model_validate(
        {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": None}).input_tokens == 0
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, _upstream, _ledger = served(no_usage(1))
    message = _message(_anthropic(url, raw)[1])
    assert (message.usage.input_tokens, message.usage.output_tokens) == (0, 0)
    assert message.model_extra["x_flywheel"] == {"usage_reported": False}
    assert keys.row("ci-bot")["totals"]["estimated_tokens"] == 7


def test_the_openai_model_allows_null_usage_so_responses_sends_null(keyed, served):
    sdk = pytest.importorskip("openai")
    pydantic = pytest.importorskip("pydantic")
    from openai.types.responses import Response, ResponseUsage
    assert Response.model_fields["usage"].is_required() is False
    with pytest.raises(pydantic.ValidationError):
        ResponseUsage.model_validate({"input_tokens": None, "output_tokens": None,
                                      "total_tokens": None})
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, _upstream, _ledger = served(no_usage(1))
    response = _openai(url, raw)[1].responses.create(model="gpt-5.3-codex", input="What changed?")
    assert response.usage is None and response.output_text == TEXT
    assert response.model_extra["x_flywheel"] == {"usage_reported": False}
    assert sdk.types.responses.Response.model_validate(response.model_dump()).usage is None
