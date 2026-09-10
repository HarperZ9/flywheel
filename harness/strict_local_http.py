"""Opt-in numeric loopback HTTP with bounded network stages and no retries.

Observers are trusted synchronous, nonblocking code; socket deadlines cannot
preempt them. Send intent/progression never proves remote acceptance or usage.
"""
from __future__ import annotations

from dataclasses import dataclass
import http.client
import ipaddress
import math
import socket
import sys
import time
from urllib.parse import urlsplit
from uuid import uuid4

from .cross_harness_adapters import _json_object
from .provider_transport_error import MalformedProviderOutput


class StrictLocalHTTPError(OSError):
    """Fixed safe code plus in-memory progression, not a persisted receipt."""

    def __init__(self, code, terminal_event=None):
        super().__init__(code)
        self.code = code
        self.terminal_event = terminal_event


class StrictLocalHTTPTimeout(StrictLocalHTTPError, TimeoutError):
    pass


def _positive_time(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value > 0
    except OverflowError:
        return False


@dataclass(frozen=True)
class StrictLocalHTTPPolicy:
    origin: str
    allowed_routes: frozenset[tuple[str, str]]
    max_request_bytes: int = 256 << 10
    max_response_bytes: int = 1 << 20  # Entire received HTTP wire, including headers.
    max_timeout_seconds: float = 60.0

    def __post_init__(self):
        try:
            parts = urlsplit(self.origin)
            address = ipaddress.ip_address(parts.hostname)
            host = f'[{address}]' if address.version == 6 else str(address)
            if (not address.is_loopback or not parts.port or
                    self.origin != f'http://{host}:{parts.port}'):
                raise ValueError
            routes = frozenset(tuple(pair) for pair in self.allowed_routes)
            if not routes:
                raise ValueError
            for method, path in routes:
                if (method not in {'GET', 'POST'} or not isinstance(path, str) or
                        not path.startswith('/') or '//' in path or
                        any(c in path for c in '%?#\\') or len(path) > 1024 or
                        any(ord(c) < 33 or ord(c) > 126 for c in path) or
                        any(part in {'.', '..'} for part in path.split('/'))):
                    raise ValueError
            for cap in (self.max_request_bytes, self.max_response_bytes):
                if type(cap) is not int or not 0 < cap < sys.maxsize:
                    raise ValueError
            if (not _positive_time(self.max_timeout_seconds) or
                    self.max_timeout_seconds > 86400):
                raise ValueError
        except (ValueError, TypeError, AttributeError, OverflowError):
            raise ValueError('invalid_strict_local_http_policy') from None
        object.__setattr__(self, 'allowed_routes', routes)


class _Attempt:
    def __init__(self, method, path, deadline, observer):
        self.base = dict(attempt_id=str(uuid4()), method=method, path=path)
        self.deadline, self.observer = deadline, observer
        self.connection_started = self.request_send_started = False
        self.observer_failed = False

    def remaining(self):
        value = self.deadline - time.monotonic()
        if value <= 0:
            raise StrictLocalHTTPTimeout('deadline_exceeded')
        return value

    def event(self, phase, outcome=None, code=None, status=None):
        return dict(self.base, phase=phase, connection_started=self.connection_started,
                    request_send_started=self.request_send_started,
                    outcome=outcome, code=code, status=status)

    def emit(self, event):
        if self.observer is not None:
            try:
                self.observer(dict(event))
            except Exception:
                self.observer_failed = True
                raise StrictLocalHTTPError('observer_failed') from None

    def before(self, phase):
        self.remaining()
        self.emit(self.event(phase))
        self.remaining()


class _DeadlineSocket(socket.socket):
    def __init__(self, family, attempt, response_cap):
        super().__init__(family, socket.SOCK_STREAM)
        self.attempt, self.response_cap = attempt, response_cap
        self.received = 0

    def connect(self, address):
        self.attempt.before('connection_attempt')
        self.settimeout(self.attempt.remaining())
        self.attempt.connection_started = True
        return super().connect(address)

    def sendall(self, data, flags=0):
        if not self.attempt.request_send_started:
            self.attempt.before('request_send_started')
        self.settimeout(self.attempt.remaining())
        self.attempt.request_send_started = True
        return super().sendall(data, flags)

    def recv_into(self, buffer, nbytes=0, flags=0):
        self.settimeout(self.attempt.remaining())
        size = min(nbytes or len(buffer), self.response_cap - self.received + 1)
        count = super().recv_into(buffer, size, flags)
        self.received += count
        if self.received > self.response_cap:
            raise StrictLocalHTTPError('response_too_large')
        return count


class _Connection(http.client.HTTPConnection):
    def __init__(self, policy, attempt):
        parts = urlsplit(policy.origin)
        super().__init__(parts.hostname, parts.port, timeout=attempt.remaining())
        self.policy, self.attempt = policy, attempt

    def connect(self):
        # No create_connection, resolver, proxy, tunnel, or address fallback.
        family = socket.AF_INET6 if ':' in self.host else socket.AF_INET
        self.sock = _DeadlineSocket(family, self.attempt, self.policy.max_response_bytes)
        self.sock.connect((self.host, self.port))


def _preflight(policy, method, url, body, timeout):
    if type(method) is not str or type(url) is not str:
        raise StrictLocalHTTPError('route_not_allowed')
    path = next((p for m, p in policy.allowed_routes
                 if method == m and url == policy.origin + p), None)
    if path is None:
        raise StrictLocalHTTPError('route_not_allowed')
    if body is not None and type(body) is not bytes:
        raise StrictLocalHTTPError('invalid_request_body')
    if body is not None and len(body) > policy.max_request_bytes:
        raise StrictLocalHTTPError('request_too_large')
    if not _positive_time(timeout):
        raise StrictLocalHTTPError('invalid_timeout')
    return path


def _exchange(policy, attempt, body):
    conn, response = _Connection(policy, attempt), None
    try:
        conn.request(attempt.base['method'], attempt.base['path'], body=body,
                     headers={'Content-Type': 'application/json', 'Connection': 'close'})
        response = conn.getresponse()
        if 300 <= response.status < 400:
            raise StrictLocalHTTPError('redirect_not_allowed')
        raw = response.read(policy.max_response_bytes + 1)
        if len(raw) > policy.max_response_bytes:
            raise StrictLocalHTTPError('response_too_large')
        # read(amt) can return short content without raising IncompleteRead.
        if response.length not in (None, 0):
            raise StrictLocalHTTPError('invalid_http_response')
        attempt.remaining()
        result = _json_object(raw.decode('utf-8'))
        attempt.remaining()
        return response.status, result
    finally:
        if response is not None:
            response.close()
        conn.close()


def _normalize(exc):
    if isinstance(exc, StrictLocalHTTPError):
        return exc
    if isinstance(exc, TimeoutError):
        return StrictLocalHTTPTimeout('deadline_exceeded')
    if isinstance(exc, (UnicodeError, MalformedProviderOutput)):
        return StrictLocalHTTPError('invalid_json_response')
    if isinstance(exc, http.client.HTTPException):
        return StrictLocalHTTPError('invalid_http_response')
    if isinstance(exc, OverflowError):
        return StrictLocalHTTPError('invalid_transport_limit')
    return StrictLocalHTTPError('network_error')


def make_strict_local_http(policy: StrictLocalHTTPPolicy, *, observer=None):
    """Return the existing Transport signature; defaults elsewhere stay unchanged.

    Intent callbacks precede syscalls. Terminal progression records attempted
    connect/send, never receiver acceptance. A failed recorder is not retried;
    the exception's terminal_event is in-memory evidence only.
    """
    if type(policy) is not StrictLocalHTTPPolicy or (observer is not None and not callable(observer)):
        raise ValueError('invalid_strict_local_http_factory')

    def transport(method, url, body, timeout):
        started = time.monotonic()
        path = _preflight(policy, method, url, body, timeout)
        attempt = _Attempt(method, path, started + min(timeout, policy.max_timeout_seconds), observer)
        try:
            status, result = _exchange(policy, attempt, body)
            attempt.emit(attempt.event('terminal', 'response', 'response_received', status))
            # No further I/O: recorder latency cannot change the network outcome.
            return status, result
        except (OSError, http.client.HTTPException, UnicodeError, MalformedProviderOutput, OverflowError) as exc:
            failure = _normalize(exc)
            outcome = 'timeout' if isinstance(failure, TimeoutError) else 'error'
            terminal = attempt.event('terminal', outcome, failure.code)
            if not attempt.observer_failed:
                try:
                    attempt.emit(terminal)
                except StrictLocalHTTPError as recorder_error:
                    failure = recorder_error
                    terminal = attempt.event('terminal', 'error', failure.code)
            failure.terminal_event = terminal
            raise failure from None

    return transport
