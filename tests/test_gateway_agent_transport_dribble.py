"""Real HTTP bytes with read acknowledgements and a separate logical clock.

This measures aggregate deadline checks, not a 150 ms wall-time performance
claim. The unchanged three-second HTTP timeout and bounded teardown guard hangs.
"""
import io
import json
import queue
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from harness.gateway_agent_transport import AgentTransportError
from tests.test_gateway_agent_transport import send, transport


class ControlledDribble:
    deadline = 10
    body = b'{"model":"selected"}'

    def __init__(self, *, before_open=None, record_reads=True):
        self.now = 0
        self.requests, self.received, self.read_times, self.sent = [], [], [], []
        self.opens, self.read_count = 0, 0
        self.accepted, self.stopped, self.finished = (threading.Event() for _ in range(3))
        self.acks, self.written = queue.Queue(), queue.Queue()
        self.before_open, self.record_reads = before_open, record_reads
        self.delegate = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def clock(self):
        return self.now

    def __enter__(self):
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                try:
                    payload = self.rfile.read(int(self.headers['Content-Length']))
                    fixture.requests.append((self.path, json.loads(payload)))
                    fixture.accepted.set()
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(fixture.body)))
                    self.end_headers()
                    for byte in fixture.body:
                        if fixture.stopped.is_set():
                            break
                        chunk = bytes([byte])
                        self.wfile.write(chunk)
                        self.wfile.flush()
                        fixture.sent.append(chunk)
                        fixture.written.put(chunk)
                        # One byte per release means read1 cannot coalesce chunks.
                        if fixture.acks.get(timeout=3) != chunk:
                            break
                except (OSError, queue.Empty):
                    pass
                finally:
                    fixture.finished.set()

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.origin = f'http://127.0.0.1:{self.server.server_port}'
        self.thread = threading.Thread(
            target=lambda: self.server.serve_forever(poll_interval=0.01), daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        started = time.monotonic()
        self.stopped.set()
        self.acks.put(None)
        closer = threading.Thread(target=self.server.shutdown, daemon=True)
        closer.start()
        closer.join(timeout=2)
        assert not closer.is_alive(), 'fixture shutdown did not complete'
        self.server.server_close()
        self.thread.join(timeout=2)
        assert not self.thread.is_alive(), 'fixture server did not stop'
        if self.accepted.is_set():
            assert self.finished.wait(timeout=2), 'fixture handler did not stop'
        assert time.monotonic() - started < 5, 'fixture teardown exceeded wall safety bound'

    def open(self, request, timeout):
        self.opens += 1
        assert timeout == 3
        assert self.clock() == 0, 'response scenario must start before logical progress'
        if self.before_open:
            self.before_open(self)
        assert self.clock() == 0, 'setup must not consume logical response budget'
        response = self.delegate.open(request, timeout=timeout)
        assert self.accepted.is_set(), 'no accepted request behind the response'
        return ObservedResponse(response, self)

    def assert_expired_after_reads(self, call, error):
        assert error.code == 'OPERATION_DEADLINE_EXCEEDED'
        assert self.accepted.is_set(), 'deadline without an accepted request'
        assert self.opens == call.calls == len(self.requests) == 1
        assert self.requests[0][0] == '/chat/completions'
        assert self.received == [b'{', b'"', b'm'], 'missing actual response progress'
        assert self.read_times == [1, 2, 10]
        assert self.sent[:3] == self.received, 'response bytes lack matching wire writes'
        assert self.now == self.deadline == 10


class ObservedResponse:
    def __init__(self, response, fixture):
        self.response, self.fixture = response, fixture
        self.status = response.status

    @property
    def fp(self):
        return self.response.fp

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.response.close()

    def read1(self, count):
        chunk = self.response.read1(count)
        if chunk:
            fixture = self.fixture
            assert fixture.written.get(timeout=3) == chunk, 'read lacks matching server write'
            fixture.read_count += 1
            # Remaining stays above the unchanged HTTP timeout before the last
            # chosen chunk; only verified reads advance this scenario's clock.
            fixture.now = (1, 2, 10)[min(fixture.read_count, 3) - 1]
            if fixture.record_reads:
                fixture.received.append(chunk)
                fixture.read_times.append(fixture.now)
            fixture.acks.put(chunk)
        return chunk


def run_dribble(fixture):
    call = transport(fixture.origin, deadline=fixture.deadline,
                     clock=fixture.clock, opener=fixture)
    with pytest.raises(AgentTransportError) as error:
        send(call, fixture.origin, timeout=3)
    return call, error.value


def test_setup_delay_cannot_consume_response_scenario_clock():
    def setup_delay(fixture):
        assert not fixture.accepted.is_set() and fixture.clock() == 0
        time.sleep(0.2)  # The setup delay that reproduced the original CI failure.
        assert not fixture.accepted.is_set() and fixture.clock() == 0

    with ControlledDribble(before_open=setup_delay) as fixture:
        call, error = run_dribble(fixture)
        fixture.assert_expired_after_reads(call, error)


def test_preconnect_expiry_cannot_pass_as_real_response_progress():
    with ControlledDribble() as fixture:
        fixture.now = fixture.deadline
        call, error = run_dribble(fixture)
        assert error.code == 'OPERATION_DEADLINE_EXCEEDED'
        assert fixture.opens == call.calls == 0
        assert fixture.requests == fixture.received == fixture.sent == []
        with pytest.raises(AssertionError, match='without an accepted request'):
            fixture.assert_expired_after_reads(call, error)


def test_missing_read_observations_cannot_pass_the_dribble_oracle():
    with ControlledDribble(record_reads=False) as fixture:
        call, error = run_dribble(fixture)
        assert fixture.accepted.is_set() and fixture.read_count == 3
        assert error.code == 'OPERATION_DEADLINE_EXCEEDED'
        with pytest.raises(AssertionError, match='missing actual response progress'):
            fixture.assert_expired_after_reads(call, error)


def test_fabricated_read_progress_without_http_cannot_pass_the_oracle():
    with ControlledDribble() as fixture:
        # A fabricated, byte-at-a-time response can manufacture the right clock
        # ticks and error, but still lacks a request and server wire evidence.
        class FakeResponse(io.BytesIO):
            status = 200

            def read1(self, count):
                chunk = super().read1(1)
                fixture.received.append(chunk)
                fixture.now = (1, 2, 10)[len(fixture.received) - 1]
                fixture.read_times.append(fixture.now)
                return chunk

        class FakeOpener:
            def open(self, request, timeout):
                return FakeResponse(fixture.body)

        call = transport(fixture.origin, deadline=fixture.deadline,
                         clock=fixture.clock, opener=FakeOpener())
        with pytest.raises(AgentTransportError) as error:
            send(call, fixture.origin)
        assert fixture.received == [b'{', b'"', b'm']
        assert error.value.code == 'OPERATION_DEADLINE_EXCEEDED'
        with pytest.raises(AssertionError, match='without an accepted request'):
            fixture.assert_expired_after_reads(call, error.value)
