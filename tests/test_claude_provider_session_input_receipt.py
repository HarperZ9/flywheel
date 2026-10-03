from harness import claude_provider_session_shapes as shapes
from harness.claude_session_transport import ClaudeSessionTransportError

from test_claude_provider_session_support import (
    Events,
    FakeClient,
    adapter_for,
    operation,
    request,
)


HELLO_INPUT_SHA256 = "5aa762ae383fbb727af3c7a36d4940a5b8c40a989452d2304fc958ff3f354e7a"


def test_input_receipt_hashes_user_input_without_claiming_provider_acceptance():
    receipt = shapes.input_receipt(request(operation(source_operation_ref="op_source")))

    assert receipt == {
        "native_request_id": "msg-1",
        "client_user_message_id": "msg-1",
        "input_sha256": HELLO_INPUT_SHA256,
        "input_kind": "text",
        "source_operation_ref": "op_source",
    }


def test_adapter_emits_input_receipt_before_uncertain_write_failure():
    client = FakeClient(write_error=ClaudeSessionTransportError(
        "write_uncertain", "frame may have reached provider"))
    events = Events()

    outcome = adapter_for(client).start_turn(
        request(operation()), emit=events, request_approval=lambda r: None,
        cancelled=lambda: False)

    assert outcome.state == "failed"
    assert outcome.result["side_effect_status"] == "write_uncertain"
    assert events.events[0]["phase"] == "native_binding"
    assert events.events[1]["phase"] == "input_receipt"
    assert events.events[1]["input_sha256"] == HELLO_INPUT_SHA256
    assert events.events[1]["input_kind"] == "text"
    assert "input_sent" not in [event["phase"] for event in events.events]
