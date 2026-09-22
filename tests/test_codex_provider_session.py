import json
import queue
import threading

from harness.codex_provider_session import CodexProviderSessionAdapter
from harness.codex_session_client import CodexSessionClient
from harness.codex_session_transport import CodexSessionTransport
from harness.provider_session_contract import (
    ProviderOperationRequest,
    ProviderRuntimeBinding,
)


OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "a" * 32


class Inbound:
    def __init__(self):
        self.lines = queue.Queue()

    def push(self, message):
        raw = json.dumps(message, separators=(",", ":")).encode("utf-8")
        self.lines.put(raw + b"\n")

    def eof(self):
        self.lines.put(b"")

    def readline(self, limit=-1):
        return self.lines.get(timeout=1.0)

    def close(self):
        self.eof()


class Outbound:
    def __init__(self):
        self.lines = queue.Queue()

    def write(self, chunk):
        self.lines.put(bytes(chunk))
        return len(chunk)

    def flush(self):
        pass

    def read_message(self):
        return json.loads(self.lines.get(timeout=1.0).decode("utf-8"))

    def close(self):
        pass


class Server:
    def __init__(self):
        self.incoming = Inbound()
        self.outgoing = Outbound()
        self.transport = CodexSessionTransport(
            self.outgoing, self.incoming, default_timeout=0.5)
        self.client = CodexSessionClient(self.transport)
        self.seen = []

    def request(self, method):
        message = self.outgoing.read_message()
        self.seen.append(message)
        assert message["method"] == method
        return message

    def reply(self, message, result):
        self.incoming.push({"id": message["id"], "result": result})

    def notify(self, method, params):
        self.incoming.push({"method": method, "params": params})

    def run(self, target):
        thread = threading.Thread(target=target, args=(self,), daemon=True)
        thread.start()
        return thread


class Events:
    def __init__(self):
        self.events = []

    def native(self, phase, **payload):
        self.events.append({"phase": phase, **payload})


def binding():
    return ProviderRuntimeBinding(
        provider="codex", workspace_ref="workspace-a",
        config_digest="cfg-a", capability_digest="cap-a")


def adapter_for(server):
    return CodexProviderSessionAdapter(
        client_supplier=lambda: server.client,
        transport_supplier=lambda: server.transport,
        runtime_binding_supplier=binding,
        idle_timeout_s=0.5,
    )


def operation(**changes):
    value = {
        "provider": "codex",
        "workspace_ref": "workspace-a",
        "config_digest": "cfg-a",
        "capability_digest": "cap-a",
        "permission_scope": {"mode": "manual"},
        "input": [{"type": "input_text", "text": "hi"}],
        "stream": True,
        "resume_policy": "new_thread",
        "timeout_s": 1,
    }
    value.update(changes)
    return value


def request(op, source=None, ref="op_" + "1" * 32):
    return ProviderOperationRequest(
        OWNER, JOURNEY, ref, "provider.session.turn", op, source)


def thread_result(thread_id="thread-1", session_id="session-1", turns=None):
    return {"thread": {
        "id": thread_id,
        "sessionId": session_id,
        "turns": list(turns or []),
        "status": {"type": "idle"},
        "cliVersion": "0.144.6",
        "createdAt": 1,
        "updatedAt": 1,
        "cwd": "C:/repo",
        "ephemeral": False,
        "modelProvider": "openai",
        "preview": [],
        "source": "appServer",
    }}


def turn(turn_id, status="completed"):
    return {"id": turn_id, "status": status, "items": []}


def finish_turn(server, turn_id, *, wrong_turn=False):
    if wrong_turn:
        server.notify("turn/started", {
            "threadId": "thread-1", "turn": turn("turn-other", "inProgress")})
    server.notify("turn/started", {
        "threadId": "thread-1", "turn": turn(turn_id, "inProgress")})
    server.notify("agent/message/delta", {
        "threadId": "thread-1", "turnId": turn_id,
        "itemId": "item-1", "delta": "hello"})
    server.notify("turn/completed", {
        "threadId": "thread-1", "turn": turn(turn_id)})


def test_codex_adapter_starts_native_thread_then_resumes_same_thread():
    first = Server()

    def first_script(server):
        server.reply(server.request("thread/start"), thread_result())
        server.reply(server.request("turn/start"), {"turn": turn("turn-1", "inProgress")})
        finish_turn(server, "turn-1", wrong_turn=True)

    first_thread = first.run(first_script)
    events = Events()
    outcome = adapter_for(first).start_turn(
        request(operation()), emit=events, request_approval=lambda r: None,
        cancelled=lambda: False)
    first_thread.join(timeout=1.0)

    assert outcome.state == "completed"
    source = outcome.result["provider_session"]
    assert source["native_session_id"] == "session-1"
    assert source["native_thread_id"] == "thread-1"
    assert source["native_turn_id"] == "turn-1"
    assert outcome.result["history_status"] == "complete"
    assert outcome.result["side_effect_status"] == "input_sent"
    assert [m["method"] for m in first.seen] == ["thread/start", "turn/start"]
    assert first.seen[1]["params"]["input"] == [{"type": "text", "text": "hi"}]
    assert any(e["phase"] == "ignored_native_event" for e in events.events)
    assert any(e.get("raw_event_type") == "agent/message/delta" for e in events.events)

    second = Server()

    def second_script(server):
        resume = server.request("thread/resume")
        assert resume["params"]["threadId"] == "thread-1"
        server.reply(resume, thread_result(turns=[turn("turn-1")]))
        start = server.request("turn/start")
        assert start["params"]["threadId"] == "thread-1"
        server.reply(start, {"turn": turn("turn-2", "inProgress")})
        finish_turn(server, "turn-2")

    second_thread = second.run(second_script)
    second_outcome = adapter_for(second).start_turn(
        request(operation(
            resume_policy="resume_after_reconcile",
            source_operation_ref="op_" + "1" * 32,
            native_thread_id="thread-1"), source, ref="op_" + "2" * 32),
        emit=Events(), request_approval=lambda r: None,
        cancelled=lambda: False)
    second_thread.join(timeout=1.0)

    assert second_outcome.state == "completed"
    assert second_outcome.result["provider_session"]["native_turn_id"] == "turn-2"
    assert second_outcome.result["native_history"][0]["id"] == "turn-1"


def test_codex_adapter_interrupts_turn_and_keeps_ack_separate_from_outcome():
    server = Server()

    def script(server):
        server.reply(server.request("thread/start"), thread_result())
        server.reply(server.request("turn/start"), {"turn": turn("turn-1", "inProgress")})
        interrupt = server.request("turn/interrupt")
        assert interrupt["params"] == {"threadId": "thread-1", "turnId": "turn-1"}
        server.reply(interrupt, {})
        server.notify("turn/completed", {
            "threadId": "thread-1", "turn": turn("turn-1", "interrupted")})

    thread = server.run(script)
    checks = iter([False, True, True])
    outcome = adapter_for(server).start_turn(
        request(operation()), emit=Events(), request_approval=lambda r: None,
        cancelled=lambda: next(checks))
    thread.join(timeout=1.0)

    assert outcome.state == "failed"
    assert outcome.result["reason"] == "AGENT_NATIVE_CANCELLED"
    assert outcome.result["cancellation_status"] == "acknowledged"
    assert outcome.result["cancellation_outcome"] == "interrupted"
