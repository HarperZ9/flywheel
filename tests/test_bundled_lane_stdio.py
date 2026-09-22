"""The raw child process enforces admission before invoking a lane handler."""
import io
import json
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("lane", ("relay", "mneme", "plexus"))
def test_stdio_filters_discovery_and_blocks_calls_before_handler(lane):
    from harness.bundled_lane_stdio import serve_admitted_lane

    calls = []
    allowed = (f"{lane}.status",)
    denied = "local_agent_start" if lane == "relay" else f"{lane}.write"

    def handle(request):
        calls.append(request)
        result = ({"tools": [{"name": allowed[0]}, {"name": denied}]}
                  if request["method"] == "tools/list" else {"ok": True})
        return {"jsonrpc": "2.0", "id": request["id"], "result": result}

    module = SimpleNamespace(**{("handle_request" if lane == "mneme" else "handle"): handle})
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": denied}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": allowed[0]}},
        {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": denied}},
        {"jsonrpc": "2.0", "id": 4, "method": "unchecked/execute"},
    ]
    output = io.StringIO()
    assert serve_admitted_lane(module, allowed, stdin=io.StringIO(
        "\n".join(json.dumps(r) for r in requests)), stdout=output) == 0
    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    assert responses[0]["result"]["tools"] == [{"name": allowed[0]}]
    assert responses[1]["error"]["message"] == "CAPABILITY_NOT_ADMITTED"
    assert responses[2]["result"] == {"ok": True}
    assert responses[3]["error"]["code"] == -32601
    assert [request["id"] for request in calls] == [1, 3]


def test_malformed_and_oversized_requests_never_reach_handler():
    from harness.bundled_lane_stdio import MAX_REQUEST_CHARS, serve_admitted_lane

    def forbidden(request):
        raise AssertionError("malformed input reached handler")

    output = io.StringIO()
    module = SimpleNamespace(handle=forbidden)
    assert serve_admitted_lane(module, (), stdin=io.StringIO("[]\n{\n"), stdout=output) == 0
    assert [json.loads(line)["error"]["code"] for line in output.getvalue().splitlines()] == [-32600, -32700]
    assert serve_admitted_lane(module, (), stdin=io.StringIO("x" * (MAX_REQUEST_CHARS + 1)), stdout=io.StringIO()) == 2
