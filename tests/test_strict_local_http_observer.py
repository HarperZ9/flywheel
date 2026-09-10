"""Observer intent is distinct from attempted I/O and remote acceptance."""
import time

import pytest

from harness.strict_local_http import StrictLocalHTTPPolicy, make_strict_local_http
from tests.strict_local_http_fixtures import server


def make(origin, observer, **limits):
    return make_strict_local_http(StrictLocalHTTPPolicy(
        origin, {('GET', '/health'), ('POST', '/generate')}, **limits), observer=observer)


def test_one_send_marker_for_header_and_body_and_distinct_call_ids():
    events = []
    with server() as fixture:
        call = make(fixture.origin, events.append)
        call('GET', fixture.origin + '/health', None, 1)
        call('POST', fixture.origin + '/generate', b'{"secret":"not-in-events"}', 1)
        assert len(fixture.connections) == len(fixture.requests) == 2
    assert len({e['attempt_id'] for e in events}) == 2
    for rows in (events[:3], events[3:]):
        assert [e['phase'] for e in rows] == ['connection_attempt', 'request_send_started', 'terminal']
        assert [(e['connection_started'], e['request_send_started']) for e in rows] == [
            (False, False), (True, False), (True, True)]
        assert rows[-1]['outcome'] == 'response' and rows[-1]['status'] == 200
        assert rows[-1]['code'] == 'response_received'
        assert set(rows[-1]) == {'attempt_id', 'phase', 'method', 'path', 'connection_started',
                               'request_send_started', 'outcome', 'code', 'status'}
    assert 'secret' not in repr(events) and 'not-in-events' not in repr(events)


@pytest.mark.parametrize('bad', ['route', 'body', 'timeout'])
def test_preflight_denial_emits_no_network_events_or_private_input(bad):
    events = []
    with server() as fixture:
        call = make(fixture.origin, events.append, max_request_bytes=4)
        with pytest.raises(OSError) as caught:
            call('POST', fixture.origin + ('/private-canary' if bad == 'route' else '/generate'),
                 b'private-canary' if bad == 'body' else b'{}', 0 if bad == 'timeout' else 1)
        assert not events and not fixture.connections
        assert caught.value.terminal_event is None
        assert 'private-canary' not in str(caught.value)


@pytest.mark.parametrize('phase', ['connection_attempt', 'request_send_started', 'terminal'])
def test_observer_failure_closes_and_preserves_progress_without_retry(phase):
    events = []

    def record(event):
        events.append(event)
        if event['phase'] == phase:
            raise RuntimeError('private-observer-canary')

    with server() as fixture:
        with pytest.raises(OSError, match='^observer_failed$') as caught:
            make(fixture.origin, record)('POST', fixture.origin + '/generate', b'{}', 1)
        terminal = caught.value.terminal_event
        assert terminal['phase'] == 'terminal' and terminal['code'] == 'observer_failed'
        assert terminal['connection_started'] == (phase != 'connection_attempt')
        assert terminal['request_send_started'] == (phase == 'terminal')
        # Allow the receiving thread to observe an already accepted socket closing.
        deadline = time.monotonic() + 0.2
        while phase != 'connection_attempt' and not fixture.connections and time.monotonic() < deadline:
            time.sleep(0.001)
        assert len(fixture.connections) == (phase != 'connection_attempt')
        assert len(fixture.requests) == (phase == 'terminal')
        assert len(events) == ['connection_attempt', 'request_send_started', 'terminal'].index(phase) + 1
        assert 'private-observer-canary' not in str(caught.value)


def test_observer_mutation_and_return_cannot_change_route_or_body():
    def record(event):
        event.update(path='/private-canary', method='DELETE', request_send_started=False)
        return {'origin': 'http://192.0.2.1:80', 'body': b'altered'}

    with server() as fixture:
        assert make(fixture.origin, record)('POST', fixture.origin + '/generate', b'{}', 1)[0] == 200
        assert fixture.requests == [{'method': 'POST', 'path': '/generate', 'body': b'{}'}]


def test_late_returning_observer_prevents_next_io_without_claiming_preemption():
    events = []

    def record(event):
        events.append(event)
        if event['phase'] == 'connection_attempt':
            time.sleep(0.06)

    with server() as fixture:
        with pytest.raises(TimeoutError) as caught:
            make(fixture.origin, record, max_timeout_seconds=0.03)('GET', fixture.origin + '/health', None, 1)
        assert not fixture.connections
        assert not caught.value.terminal_event['connection_started']
        assert [e['phase'] for e in events] == ['connection_attempt', 'terminal']


def test_timeout_after_send_reports_unknown_delivery_once():
    events = []
    with server(lambda sock, row, stop: stop.wait(2)) as fixture:
        with pytest.raises(TimeoutError) as caught:
            make(fixture.origin, events.append, max_timeout_seconds=0.05)(
                'POST', fixture.origin + '/generate', b'{}', 1)
        assert len(fixture.connections) == len(fixture.requests) == 1
        assert events[-1] == caught.value.terminal_event
        assert events[-1]['outcome'] == 'timeout' and events[-1]['request_send_started']
        assert len(events) == 3


def test_terminal_observer_does_not_reclassify_completed_network_work():
    events = []

    def record(event):
        events.append(event)
        if event['phase'] == 'terminal':
            time.sleep(0.06)

    with server() as fixture:
        assert make(fixture.origin, record, max_timeout_seconds=0.04)(
            'GET', fixture.origin + '/health', None, 1) == (200, {'ok': True})
        assert len(events) == 3 and events[-1]['outcome'] == 'response'
        assert len(fixture.requests) == 1
