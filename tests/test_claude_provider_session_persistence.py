import json

from harness.claude_provider_session import ClaudeProviderSessionAdapter
from harness.claude_session_client import ClaudeSessionClient
from harness.claude_session_contract import build_claude_session_argv

from test_claude_session_client import FakeProcess, initialized_launcher
from test_claude_provider_session_support import (
    Events,
    FakeClient,
    OPREF,
    adapter_for,
    binding,
    operation,
    request,
    result_event,
)


SOURCE = {
    "provider": "claude",
    "native_session_id": "session-a",
    "native_thread_id": "",
    "native_turn_id": "",
    "last_provider_event_id": "event-9",
    "config_digest": "cfg-a",
    "capability_digest": "cap-a",
}


def resumed_operation(**changes):
    value = operation(
        resume_policy="resume_after_reconcile",
        source_operation_ref=OPREF,
        input="second turn",
    )
    value.update(changes)
    return value


def test_resume_after_reconcile_uses_source_session_and_sends_only_new_input():
    client = FakeClient(events=[result_event("session-a")])
    events = Events()

    outcome = adapter_for(client).start_turn(
        request(resumed_operation(), source=SOURCE), emit=events,
        request_approval=lambda r: None, cancelled=lambda: False)

    assert outcome.state == "completed"
    assert client.sent == [("text", "second turn")]
    assert outcome.result["provider_session"]["native_session_id"] == "session-a"
    binding = next(event for event in events.events if event["phase"] == "native_binding")
    assert binding["native_session_id"] == "session-a"
    receipt = next(event for event in events.events if event["phase"] == "input_receipt")
    assert receipt["source_operation_ref"] == OPREF


def test_resume_after_reconcile_rejects_missing_source_session_before_input():
    client = FakeClient(events=[result_event("session-a")])
    source = {**SOURCE, "native_session_id": ""}

    outcome = adapter_for(client).start_turn(
        request(resumed_operation(), source=source), emit=Events(),
        request_approval=lambda r: None, cancelled=lambda: False)

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_BINDING_DRIFT"
    assert client.sent == []


def test_resume_after_reconcile_rejects_non_claude_source_before_input():
    client = FakeClient(events=[result_event("session-a")])
    source = {**SOURCE, "provider": "codex"}

    outcome = adapter_for(client).start_turn(
        request(resumed_operation(), source=source), emit=Events(),
        request_approval=lambda r: None, cancelled=lambda: False)

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_BINDING_DRIFT"
    assert client.sent == []


def test_resume_after_reconcile_rejects_source_binding_drift_before_input():
    client = FakeClient(events=[result_event("session-a")])
    source = {**SOURCE, "config_digest": "cfg-other"}

    outcome = adapter_for(client).start_turn(
        request(resumed_operation(), source=source), emit=Events(),
        request_approval=lambda r: None, cancelled=lambda: False)

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_BINDING_DRIFT"
    assert client.sent == []


def test_resume_after_reconcile_passes_launch_config_to_injected_client_supplier():
    client = FakeClient(events=[result_event("session-a")])
    observed = []

    def supplier(config):
        observed.append(config)
        return client

    adapter = adapter_for(client)
    adapter._client_supplier = supplier

    outcome = adapter.start_turn(
        request(resumed_operation(), source=SOURCE), emit=Events(),
        request_approval=lambda r: None, cancelled=lambda: False)

    assert outcome.state == "completed"
    assert observed[0].resume_session_id == "session-a"
    assert "--resume=session-a" in build_claude_session_argv(observed[0])


def test_resume_after_reconcile_real_client_uses_resume_argv_and_only_new_stdin():
    process = FakeProcess()
    launcher = initialized_launcher(process)
    launcher.after_message(2, result_event("session-a").raw)
    observed = []

    def supplier(config):
        observed.append(config)
        return ClaudeSessionClient.start(
            config, launcher=launcher, initialize_timeout=1.0)

    adapter = ClaudeProviderSessionAdapter(
        client_supplier=supplier,
        transport_supplier=None,
        runtime_binding_supplier=binding,
        idle_timeout_s=1.0,
        max_events=16,
    )

    outcome = adapter.start_turn(
        request(resumed_operation(), source=SOURCE), emit=Events(),
        request_approval=lambda r: None, cancelled=lambda: False)

    assert outcome.state == "completed"
    assert observed[0].resume_session_id == "session-a"
    assert "--resume=session-a" in launcher.calls[0]["argv"]
    frames = process.stdin.wait_messages(2)
    assert frames[1]["message"]["content"] == "second turn"
    assert "hello" not in json.dumps(frames[1])

