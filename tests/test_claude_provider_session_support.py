from harness.claude_provider_session import ClaudeProviderSessionAdapter
from harness.claude_session_contract import (
    ClaudeControlRequest,
    ClaudeSessionEvent,
)
from harness.provider_session_contract import (
    ProviderOperationRequest,
    ProviderRuntimeBinding,
)

OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "a" * 32
OPREF = "op_" + "1" * 32


class Events:
    def __init__(self):
        self.events = []

    def native(self, phase, **payload):
        self.events.append({"phase": phase, **payload})


class FakeClient:
    def __init__(self, *, events=(), controls=(), protocols=(), write_error=None,
                 event_error=None):
        self.events = list(events)
        self.controls = list(controls)
        self.protocols = list(protocols)
        self.write_error = write_error
        self.event_error = event_error
        self.sent = []
        self.decisions = []
        self.interrupt_calls = 0
        self.pending_controls = 0
        self.recovery_needed = False

    def send_text(self, text):
        self.sent.append(("text", text))
        if self.write_error is not None:
            raise self.write_error

    def send_blocks(self, blocks):
        self.sent.append(("blocks", list(blocks)))
        if self.write_error is not None:
            raise self.write_error

    def next_event(self, timeout=None):
        if self.event_error is not None:
            raise self.event_error
        return self.events.pop(0) if self.events else None

    def next_control_request(self, timeout=None):
        if not self.controls:
            return None
        self.pending_controls += 1
        return self.controls.pop(0)

    def next_protocol_event(self, timeout=None):
        return self.protocols.pop(0) if self.protocols else None

    def send_permission_decision(self, request, decision):
        self.decisions.append((request, decision))
        self.pending_controls = max(0, self.pending_controls - 1)

    def has_pending_control_requests(self):
        return self.pending_controls > 0

    def mark_recovery_needed(self):
        self.recovery_needed = True

    def interrupt(self, timeout=None):
        self.interrupt_calls += 1
        return {"acknowledged": True}


def binding():
    return ProviderRuntimeBinding(
        provider="claude", workspace_ref="workspace-a",
        config_digest="cfg-a", capability_digest="cap-a")


def adapter_for(client, **kw):
    called = {"launcher": 0}

    def launcher():
        called["launcher"] += 1

    transport_supplier = kw.pop("transport_supplier", lambda: client)
    adapter = ClaudeProviderSessionAdapter(
        client_supplier=lambda: client,
        transport_supplier=transport_supplier,
        runtime_binding_supplier=binding,
        launcher_supplier=launcher,
        idle_timeout_s=0.01,
        max_events=8,
        **kw,
    )
    adapter.launcher_calls = called
    return adapter


def operation(**changes):
    value = {
        "provider": "claude",
        "workspace_ref": "workspace-a",
        "config_digest": "cfg-a",
        "capability_digest": "cap-a",
        "permission_scope": {"mode": "manual"},
        "input": "hello",
        "resume_policy": "new_thread",
        "client_user_message_id": "msg-1",
        "timeout_s": 1,
    }
    value.update(changes)
    return value


def request(op, *, source=None, action="provider.session.turn", ref=OPREF):
    return ProviderOperationRequest(OWNER, JOURNEY, ref, action, op, source)


def result_event(session="claude-session-1", *, subtype="success",
                 is_error=False, sequence=1):
    return ClaudeSessionEvent(sequence, "result", {
        "type": "result", "subtype": subtype, "duration_ms": 1,
        "duration_api_ms": 1, "is_error": is_error,
        "num_turns": 1, "session_id": session,
    }, session)


def assistant_event(session="claude-session-1", *, sequence=1):
    return ClaudeSessionEvent(sequence, "assistant", {
        "type": "assistant", "session_id": session,
    }, session)


def permission_request(tool_use_id="tool-1", request_id="req-1"):
    body = {
        "subtype": "can_use_tool", "tool_name": "Bash",
        "input": {"command": "pwd"}, "tool_use_id": tool_use_id,
    }
    return ClaudeControlRequest(request_id, "can_use_tool", body, {"request": body}, "tok-1")


def tool_use_event(tool_use_id="tool-1", session="claude-session-1", *, sequence=1):
    return ClaudeSessionEvent(sequence, "assistant", {
        "type": "assistant", "session_id": session,
        "message": {"role": "assistant", "content": [{
            "type": "tool_use", "id": tool_use_id,
            "name": "Bash", "input": {"command": "pwd"},
        }]},
    }, session)


class SendOnlyClient:
    def __init__(self):
        self.sent = []

    def send_text(self, text):
        self.sent.append(("text", text))


class SurfaceAfterSession(FakeClient):
    def __init__(self):
        super().__init__()
        self.step = 0
        self.control = permission_request()

    def next_event(self, timeout=None):
        if self.step == 0:
            self.step = 1
            return tool_use_event("tool-1", "claude-session-1", sequence=1)
        if self.step == 2:
            self.step = 3
            return result_event("claude-session-1", sequence=2)
        return None

    def next_control_request(self, timeout=None):
        if self.step == 1:
            self.step = 2
            self.pending_controls += 1
            return self.control
        return None


class ControlBeforeResult(FakeClient):
    def __init__(self):
        super().__init__()
        self.step = 0
        self.control = permission_request()

    def next_event(self, timeout=None):
        if self.step == 0:
            self.step = 1
            return tool_use_event("tool-1", sequence=1)
        if self.step == 2:
            self.step = 3
            return result_event(sequence=2)
        return None

    def next_control_request(self, timeout=None):
        if self.step == 1:
            self.step = 2
            self.pending_controls += 1
            return self.control
        return None
