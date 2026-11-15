"""/api/agent: no provider contact without a record written first.

Fifth review round of 2.0.0, the lead's ruling 5. Round 4 did not examine the
gateway's agent operations for the fault it fixed on the model interfaces (a
provider call that leaves no record). This file is that examination, as
tests.

An agent run reaches a provider on two paths, and neither uses the gateway
ledger: each run has its own ledger, written record by record into the run's
private trace (harness/gateway_agent_trace.py).

  native   the provider-native tool loop (gateway_agent_native_runtime._call)
  router   the text-protocol loop, through BoundAgentProposer
           (gateway_agent_proposer)

Both append `model_inference` with phase `started` before the request leaves,
and a closing record after it: `model_inference` `response_received` or
`failed` on the native path, `model_call` on both. So the rule the model
interfaces now keep holds here already, in the run's own record: these tests
read the trace at the moment of contact and find the started record there.

The third execution mode, `native_cli_session`, starts a vendor CLI
(claude, codex). The CLI makes its own provider calls under the user's own
sign-in; Flywheel sees the CLI's events, not its requests, and cannot record
them before they leave.

The transport is a stub. No provider is called.
"""
import time

import pytest

from harness.gateway_agent_binding import freeze_agent_binding
from harness.gateway_agent_execution import run_private_agent
from harness.gateway_agent_trace import AgentTrace
from harness.gateway_operation import canonicalize_operation
from harness.plan_run_snapshot import thaw_json
from tests.test_gateway_agent_native_tools import (
    JOURNEY, OP, OWNER, ledger_rows, native_binding, native_operation)

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release

NATIVE_OK = {"id": "resp_1", "model": "gpt-6-astra", "status": "completed", "output": [
    {"type": "message", "content": [{"type": "output_text", "text": "Nothing to do."}]}]}
ROUTER_OK = {"id": "chatcmpl-1", "model": "gpt-6-astra", "choices": [{
    "index": 0, "message": {"role": "assistant", "content": "Nothing to do."},
    "finish_reason": "stop"}], "usage": {"prompt_tokens": 5, "completion_tokens": 3}}
ERROR = {"error": {"message": "overloaded", "type": "server_error"}}


def _router_binding(tmp_path):
    op = native_operation(tmp_path)
    op.pop("tool_protocol")
    return op, thaw_json(freeze_agent_binding(canonicalize_operation("agent.run", op), tmp_path))


PATHS = {
    "native": (native_binding, "harness.gateway_agent_native_tools.BoundAgentTransport",
               NATIVE_OK),
    "router": (_router_binding, "harness.gateway_agent_transport.BoundAgentTransport",
               ROUTER_OK),
}


def _run(tmp_path, monkeypatch, path, status, answer):
    """One agent run on `path` against a stub transport; (trace, what each contact saw, error)."""
    make, target, _ok = PATHS[path]
    op, binding = make(tmp_path)
    trace = AgentTrace(tmp_path, OWNER, JOURNEY, OP, secrets=("OPENAI_KEY",))
    seen = []

    class Transport:
        def __init__(self, **kwargs):
            pass

        def __call__(self, method, url, headers, body, timeout):
            seen.append([(row["meta"]["phase"], row["meta"]["ordinal"])
                         for row in ledger_rows(trace, "model_inference")])
            return status, answer
    monkeypatch.setattr(target, Transport)
    error = None
    try:
        run_private_agent(op, {"OPENAI_API_KEY": "OPENAI_KEY"}, tmp_path, trace, None,
                          lambda event: None, binding=binding, deadline=time.monotonic() + 15)
    except Exception as exc:    # noqa: BLE001 - the two paths raise different errors
        error = exc
    return trace, seen, error


@pytest.mark.parametrize("path", list(PATHS))
def test_the_started_record_is_in_the_trace_when_the_provider_is_contacted(
        tmp_path, monkeypatch, path):
    trace, seen, error = _run(tmp_path, monkeypatch, path, 200, PATHS[path][2])
    assert error is None and len(seen) == 1, (error, seen)
    assert seen[0][-1] == ("started", 1), "the request left before its started record"
    calls = ledger_rows(trace, "model_call")
    assert [row["meta"]["ordinal"] for row in calls] == [1]         # and one closing record


@pytest.mark.parametrize("path", list(PATHS))
def test_a_provider_error_on_an_agent_run_leaves_a_start_and_a_closing_record(
        tmp_path, monkeypatch, path):
    trace, seen, error = _run(tmp_path, monkeypatch, path, 500, ERROR)
    assert error is not None and seen and all(rows[-1][0] == "started" for rows in seen)
    started = [row for row in ledger_rows(trace, "model_inference")
               if row["meta"]["phase"] == "started"]
    assert len(started) == len(seen), "one started record for each contact"
    assert ledger_rows(trace, "provider_error"), "the provider's refusal is in the record"
    closing = (ledger_rows(trace, "model_call")
               + [row for row in ledger_rows(trace, "model_inference")
                  if row["meta"]["phase"] == "failed"])
    assert closing, "the failed call has no closing record"


@pytest.mark.parametrize("path", list(PATHS))
def test_an_agent_call_whose_started_record_cannot_be_written_is_not_sent(
        tmp_path, monkeypatch, path):
    """The trace refuses the started record: the transport is never called."""
    real = AgentTrace.append

    def append(self, kind, payload):
        if kind == "ledger" and payload.get("kind") == "model_inference":
            raise OSError(28, "No space left on device")
        return real(self, kind, payload)
    monkeypatch.setattr(AgentTrace, "append", append)
    _trace, seen, error = _run(tmp_path, monkeypatch, path, 200, PATHS[path][2])
    assert error is not None, "the run went on without its started record"
    assert not seen, "a provider request left with no started record"
