"""The bound transport is under the reach rule: a live-screen frame sent to a model is recorded.

Sixth review round of 2.0.0. While every route was being examined (finding S1
of the fourth independent review) one more model call turned up that neither
that review nor the first sweep had seen: `POST /api/live-screen/deliver`
sends a sampled screen frame and a prompt to a vision model through
`gateway_agent_transport.BoundAgentTransport`, in the gateway process, and
wrote its delivery record only after the provider had answered. The bound
transport has its own opener, so the rule at the other transports did not
reach it.

Now the bound transport checks the rule too. A gateway agent run, which
records each request in its own trace first, is the one caller that passes
without a ledger account (`gateway_reach.traced`, set by
`gateway_agent_execution.run_private_agent`). The frame delivery makes its
request as a ledger call. The stub stands in for the provider; the route's
HTTP body needs a live screen session and is not sent here.
"""
import time
import types

import pytest

from harness import gateway_reach
from harness.gateway_agent_transport import BoundAgentTransport
from harness.live_screen_delivery import DeliveryError, OpenAIResponsesImageTransport
from tests import gateway_messages_support as support
from tests.test_gateway_route_accounting import entries, paired, stubbed  # noqa: F401  (fixture)

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release
KEY = "sk-test-not-a-real-key"
FRAME = types.SimpleNamespace(media_type="image/png", payload=b"\x89PNG\r\n\x1a\n" + b"0" * 64)
BODY = (b'{"model":"vision-1","input":[],"max_output_tokens":64,"store":false,'
        b'"parallel_tool_calls":false,"tools":[],"stream":false,"temperature":0}')


def bound(url: str) -> BoundAgentTransport:
    return BoundAgentTransport(base_url=f"{url}/v1", adapter="openai", model="vision-1",
                               deadline=time.monotonic() + 30, max_tokens=64, max_calls=1,
                               native_protocol="openai_responses")


def image(url: str) -> OpenAIResponsesImageTransport:
    return OpenAIResponsesImageTransport(bound(url), base_url=f"{url}/v1", model="vision-1",
                                         api_key=KEY, max_output_tokens=64)


def call(transport, url: str):
    return transport("POST", f"{url}/v1/responses", {
        "content-type": "application/json", "authorization": f"Bearer {KEY}"}, BODY, 10.0)


@pytest.fixture
def provider(stubbed):  # noqa: F811
    upstream, home, _tmp = stubbed
    upstream.answers[:] = [support.json_answer({"id": "resp_1", "status": "completed",
                                                "output": []})]
    return upstream, home


def test_a_frame_sent_to_a_vision_model_is_a_ledger_call(provider):
    upstream, home = provider
    sent = image(upstream.url).send_sampled_image(frame=FRAME, prompt="What is on screen?")
    assert sent["provider_status"] == 200 and sent["provider_response_id"] == "resp_1"
    end, = paired(upstream, home)
    assert end.kind == "endpoint_call" and end.meta["endpoint"] == "openai"
    assert upstream.requests[0]["path"] == "/v1/responses"


def test_a_delivery_the_provider_refuses_leaves_a_failed_entry(provider):
    upstream, home = provider
    upstream.answers[:] = [support.json_answer({"error": {"message": "no"}}, 500)]
    with pytest.raises(DeliveryError):
        image(upstream.url).send_sampled_image(frame=FRAME, prompt="What is on screen?")
    end, = paired(upstream, home)
    assert end.kind == "endpoint_call_failed" and end.meta["reason"] == "upstream_status_500"


def test_with_the_ledger_unavailable_no_frame_is_sent(provider):
    upstream, home = provider
    gateway_reach.enforce(lambda: None)
    with pytest.raises(Exception):
        image(upstream.url).send_sampled_image(frame=FRAME, prompt="What is on screen?")
    assert upstream.requests == [] and entries(home) == []


def test_the_bound_transport_alone_is_refused_in_a_gateway_and_sends_nothing(provider):
    upstream, home = provider
    with pytest.raises(gateway_reach.Unaccounted):
        call(bound(upstream.url), upstream.url)
    assert upstream.requests == [] and entries(home) == []


def test_an_agent_run_passes_on_its_own_trace(provider):
    """`run_private_agent` wraps the run in `traced`: its requests are in the run's trace
    (tests/test_gateway_agent_contact_invariant.py), not in this ledger."""
    upstream, home = provider
    status, _obj = gateway_reach.traced(lambda: call(bound(upstream.url), upstream.url))
    assert status == 200 and len(upstream.requests) == 1 and entries(home) == []


def test_control_outside_a_gateway_the_bound_transport_is_sent(provider):
    upstream, home = provider
    gateway_reach.release()
    status, _obj = call(bound(upstream.url), upstream.url)
    assert status == 200 and len(upstream.requests) == 1 and entries(home) == []
