import json
import queue
import threading

import pytest

from harness.claude_session_contract import (
    ClaudePermissionDecision,
    ClaudeSessionContractError,
)
from harness.claude_session_transport import (
    ClaudeSessionLaunchConfig,
    ClaudeSessionTransport,
    ClaudeSessionTransportError,
    build_claude_session_argv,
)


class Inbound:
    def __init__(self):
        self._lines = queue.Queue()
        self.readline_limits = []

    def push(self, message):
        raw = json.dumps(message, separators=(",", ":")).encode("utf-8")
        self._lines.put(raw + b"\n")

    def push_raw(self, raw):
        self._lines.put(raw)

    def close(self):
        self._lines.put(b"")

    def readline(self, limit=-1):
        self.readline_limits.append(limit)
        line = self._lines.get()
        if limit is not None and limit >= 0 and len(line) > limit:
            head = line[:limit]
            tail = line[limit:]
            self._lines.put(tail)
            return head
        return line


class FailingInbound:
    def readline(self, limit=-1):
        raise OSError("pipe failed")


class Outbound:
    def __init__(self):
        self._chunks = []
        self._condition = threading.Condition()

    def write(self, chunk):
        with self._condition:
            self._chunks.append(bytes(chunk))
            self._condition.notify_all()
        return len(chunk)

    def flush(self):
        pass

    def messages(self):
        with self._condition:
            chunks = list(self._chunks)
        return [json.loads(chunk.decode("utf-8")) for chunk in chunks]

    def wait_messages(self, count):
        with self._condition:
            assert self._condition.wait_for(
                lambda: len(self._chunks) >= count, timeout=1.0)
        return self.messages()


def make_transport(**kwargs):
    incoming, outgoing = Inbound(), Outbound()
    transport = ClaudeSessionTransport(
        incoming=incoming, outgoing=outgoing, default_timeout=0.2, **kwargs)
    return transport, incoming, outgoing


def test_launch_config_uses_verbose_streaming_json_and_no_unbounded_extra_args():
    config = ClaudeSessionLaunchConfig(
        executable="claude.exe",
        working_directory="C:/work/project",
        model="sonnet",
        permission_mode="manual",
        resume_session_id="5b3f2c1a-8d4e-4f6b-9a7c-2e1d0f9b8a6c",
        fork_session=True,
    )

    argv = build_claude_session_argv(config)

    assert argv == [
        "claude.exe",
        "--print",
        "--output-format", "stream-json",
        "--verbose",
        "--input-format", "stream-json",
        "--permission-mode=manual",
        "--permission-prompt-tool", "stdio",
        "--model=sonnet",
        "--resume=5b3f2c1a-8d4e-4f6b-9a7c-2e1d0f9b8a6c",
        "--fork-session",
        "--replay-user-messages",
    ]
    with pytest.raises(TypeError):
        ClaudeSessionLaunchConfig(
            executable="claude.exe",
            extra_args=("--permission-mode", "bypassPermissions"),
        )
    with pytest.raises(ClaudeSessionContractError) as caught:
        build_claude_session_argv(ClaudeSessionLaunchConfig(
            executable="claude.exe", permission_mode="bypassPermissions"))
    assert caught.value.code == "permission_bypass_refused"


def test_queue_sizes_must_be_positive_to_avoid_unbounded_queues():
    incoming, outgoing = Inbound(), Outbound()

    with pytest.raises(ClaudeSessionTransportError) as caught:
        ClaudeSessionTransport(
            incoming=incoming, outgoing=outgoing, event_queue_size=0)

    assert caught.value.code == "invalid_queue_size"


def test_send_user_message_writes_documented_streaming_input_shape():
    transport, _incoming, outgoing = make_transport()

    transport.send_user_message("Analyze this module")

    assert outgoing.wait_messages(1) == [{
        "type": "user",
        "message": {"role": "user", "content": "Analyze this module"},
        "parent_tool_use_id": None,
    }]


def test_second_user_message_waits_for_result_to_avoid_uncorrelated_pending_state():
    transport, incoming, _outgoing = make_transport()

    transport.send_user_message("First")
    with pytest.raises(ClaudeSessionTransportError) as caught:
        transport.send_user_message("Second")
    assert caught.value.code == "turn_in_flight"

    incoming.push({"type": "result", "subtype": "success", "duration_ms": 1, "duration_api_ms": 1, "is_error": False, "num_turns": 1, "session_id": "s1"})
    assert transport.pop_event(timeout=1.0).kind == "result"
    transport.send_user_message("Second")


def test_send_user_message_accepts_text_and_base64_image_blocks_only():
    transport, _incoming, outgoing = make_transport()

    transport.send_user_message([
        {"type": "text", "text": "Review this diagram"},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": "aW1hZ2U=",
            },
        },
    ])

    assert outgoing.wait_messages(1)[0]["message"]["content"] == [
        {"type": "text", "text": "Review this diagram"},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": "aW1hZ2U=",
            },
        },
    ]
    with pytest.raises(ClaudeSessionContractError) as caught:
        transport.send_user_message([
            {"type": "file", "path": "notes.md"},
        ])
    assert caught.value.code == "unsupported_content_block"


def test_reader_preserves_raw_events_and_refuses_session_id_switch():
    transport, incoming, _outgoing = make_transport()

    incoming.push({"type": "system", "subtype": "init", "session_id": "s1"})
    incoming.push({"type": "assistant", "message": {"content": []}})
    incoming.push({"type": "result", "subtype": "success", "duration_ms": 1, "duration_api_ms": 1, "is_error": False, "num_turns": 1, "session_id": "s2"})

    init_event = transport.pop_event(timeout=1.0)
    assistant_event = transport.pop_event(timeout=1.0)
    protocol_event = transport.pop_protocol_event(timeout=1.0)

    assert init_event.kind == "system"
    assert init_event.sequence == 1
    assert init_event.session_id == "s1"
    assert assistant_event.kind == "assistant"
    assert protocol_event.kind == "session_id_mismatch"
    assert transport.session_id == "s1"
    assert transport.needs_recovery() is True


def test_malformed_line_is_fatal_and_prevents_further_input():
    transport, incoming, _outgoing = make_transport()

    incoming.push_raw(b"{not-json}\n")
    incoming.push({"type": "result", "subtype": "success", "duration_ms": 1, "duration_api_ms": 1, "is_error": False, "num_turns": 1, "session_id": "s1"})

    protocol_event = transport.pop_protocol_event(timeout=1.0)

    assert protocol_event.kind == "malformed_json"
    assert transport.needs_recovery() is True
    assert transport.pop_event(timeout=0.1) is None
    with pytest.raises(ClaudeSessionTransportError) as caught:
        transport.send_user_message("after malformed")
    assert caught.value.code == "transport_recovery_needed"


def test_event_overflow_is_fatal_and_loss_is_visible():
    transport, incoming, _outgoing = make_transport(event_queue_size=1)

    incoming.push({"type": "assistant", "message": {"content": ["first"]}})
    incoming.push({"type": "assistant", "message": {"content": ["second"]}})

    assert transport.pop_event(timeout=1.0).raw["message"]["content"] == ["first"]
    protocol_event = transport.pop_protocol_event(timeout=1.0)
    assert protocol_event.kind == "event_overflow"
    assert transport.event_overflowed() is True
    assert transport.needs_recovery() is True


def test_fatal_protocol_error_stops_reader_without_accepting_later_frames():
    transport, incoming, _outgoing = make_transport(protocol_queue_size=1)

    incoming.push_raw(b"bad-1\n")
    incoming.push({"type": "assistant", "message": {"content": ["late"]}})

    assert transport.pop_protocol_event(timeout=1.0).kind == "malformed_json"
    assert transport.pop_event(timeout=0.1) is None
    assert transport.protocol_overflowed() is False
    assert transport.needs_recovery() is True


def test_unknown_provider_event_and_read_exception_are_fatal():
    transport, incoming, _outgoing = make_transport()
    incoming.push({"type": "surprise", "session_id": "s1"})

    assert transport.pop_protocol_event(timeout=1.0).kind == "unknown_provider_event"
    assert transport.needs_recovery() is True

    outgoing = Outbound()
    failing = ClaudeSessionTransport(
        incoming=FailingInbound(), outgoing=outgoing, default_timeout=0.2)
    assert failing.pop_protocol_event(timeout=1.0).kind == "read_error"
    assert failing.needs_recovery() is True


def test_reader_uses_bounded_readline_before_accepting_line():
    transport, incoming, _outgoing = make_transport(max_line_bytes=12)

    incoming.push_raw(b'{"type":"assistant"}\n')

    protocol_event = transport.pop_protocol_event(timeout=1.0)
    assert incoming.readline_limits[0] == 13
    assert protocol_event.kind == "line_overflow"
    assert transport.needs_recovery() is True


def test_eof_before_result_marks_recovery_needed_for_pending_input():
    transport, incoming, _outgoing = make_transport()

    transport.send_user_message("Start work")
    incoming.close()

    protocol_event = transport.pop_protocol_event(timeout=1.0)
    assert protocol_event.kind == "eof"
    assert transport.needs_recovery() is True
