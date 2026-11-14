"""Helpers for the gateway Responses tests: fixtures and a normal form.

Fixtures live in fixtures/gateway_responses. `requests/` holds Responses
request bodies and `expected/` holds the Response objects, stream events and
upstream request bodies they must produce. The upstream replies are the
recordings the Messages tests already replay (fixtures/provider_streams and
fixtures/gateway_messages/upstream). All were written in the documented
formats; no provider was called to make them or to replay them.

The stub upstream, the real gateway on a loopback port and the replay backend
come from tests.gateway_messages_support.

Wire format, read 2026-11-14. platform.openai.com refused the fetch (403), so:
  https://github.com/openai/openai-openapi (manual_spec branch, openapi.yaml):
      CreateResponse, Response, ResponseUsage, the createResponse streaming
      example, ErrorResponse
  openai Python SDK 2.36.0, types/responses (generated from that spec)
  https://developers.openai.com/api/docs/guides/function-calling
  https://developers.openai.com/api/docs/guides/error-codes
"""
import json
import re
from pathlib import Path

from tests.gateway_messages_support import (  # noqa: F401  (shared with the tests)
    TOKEN, Upstream, events, gateway_server, joined, json_answer, kinds, point_at,
    replayed, stream_answer)
from tests.gateway_messages_support import load as upstream_load, raw as upstream_raw  # noqa: F401

ROOT = Path(__file__).parent / "fixtures" / "gateway_responses"
_FRESH = re.compile(r"^(resp|msg|fc)_fw_[0-9a-f]{24}")
_DROPPED = ("created_at", "x_receipt")


def load(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def normal(value):
    """A Response object or event list without what the gateway makes fresh per
    reply: the time, the receipt, and the random part of each id."""
    if isinstance(value, dict):
        return {key: normal(item) for key, item in value.items() if key not in _DROPPED}
    if isinstance(value, list):
        return [normal(item) for item in value]
    if isinstance(value, str):
        return _FRESH.sub(lambda found: f"{found.group(1)}_fw_TOKEN", value)
    return value


def nothing_sent(backend) -> bool:
    return backend.transport.requests == [] and backend.stream_transport.requests == []


def is_error(answer, status: int, kind: str) -> bool:
    """Is this answer the documented error body, with this status and type?"""
    body = answer.body
    return (answer.status == status and set(body) == {"error"}
            and set(body["error"]) == {"message", "type", "param", "code"}
            and body["error"]["type"] == kind and isinstance(body["error"]["message"], str))
