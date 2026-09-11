"""Frozen provider HTTP authority, cumulative attempts, and bounded JSON I/O.

The owned worker supervisor enforces the wall deadline even during DNS/TLS or
HTTP header parsing. This transport also checks it around every response chunk.
No provider material or credentials are included in transport error messages.
"""
from __future__ import annotations

import json
import math
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request


class AgentTransportError(ValueError):
    """Closed safe error codes that survive the backend transport guard."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fail(code='AGENT_BINDING_DRIFT'):
    raise AgentTransportError(code) from None


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError
        out[key] = value
    return out


def _finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError
    if isinstance(value, dict):
        for item in value.values():
            _finite(item)
    elif isinstance(value, list):
        for item in value:
            _finite(item)


def _object(raw):
    value = json.loads(raw, object_pairs_hook=_pairs)
    if not isinstance(value, dict):
        raise ValueError
    _finite(value)
    return value


def _positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


class BoundAgentTransport:
    """An endpoints_http-compatible callable; construct from trusted bindings.

    ``opener`` is a trusted test seam with ``open(request, timeout=...)``. Each
    attempted HTTP request consumes one call, including failed network attempts
    and provider errors. Backend retries cannot bypass this shared counter.
    """

    def __init__(self, *, base_url, adapter, model, deadline, max_tokens,
                 max_calls, clock=time.monotonic, opener=None,
                 allow_omitted_temperature=False):
        try:
            parts = urllib.parse.urlsplit(base_url)
            if (not isinstance(base_url, str) or len(base_url) > 2048 or
                    parts.scheme not in {'http', 'https'} or not parts.hostname or
                    parts.username is not None or parts.password is not None or
                    parts.query or parts.fragment or parts.port == 0 or
                    any(ord(c) < 33 or ord(c) > 126 for c in base_url) or
                    any(c in base_url for c in '\\%?#') or
                    any(p in {'.', '..'} for p in parts.path.split('/')) or
                    '//' in parts.path or base_url.endswith('/')):
                raise ValueError
            if (not isinstance(model, str) or
                    not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,159}', model) or
                    not _positive(deadline) or type(max_tokens) is not int or
                    not 1 <= max_tokens <= 65536 or type(max_calls) is not int or
                    not 1 <= max_calls <= 12 or
                    type(allow_omitted_temperature) is not bool or
                    (allow_omitted_temperature and adapter != 'anthropic')):
                raise ValueError
            suffix = {'openai': '/chat/completions', 'anthropic': '/v1/messages',
                      'gemini': '/models/' + urllib.parse.quote(model, safe='') +
                      ':generateContent'}[adapter]
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            _fail()
        self._url, self._adapter, self._model = base_url + suffix, adapter, model
        self._deadline, self._max_tokens = deadline, max_tokens
        self._max_calls, self._clock, self._calls = max_calls, clock, 0
        self._deadline_limited = False
        self._allow_omitted_temperature = allow_omitted_temperature
        self._opener = opener if opener is not None else urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _NoRedirect())

    @property
    def calls(self):
        return self._calls

    def _remaining(self):
        remaining = self._deadline - self._clock()
        if not math.isfinite(remaining) or remaining <= 0:
            _fail('OPERATION_DEADLINE_EXCEEDED')
        return remaining

    def _request(self, method, url, headers, body, timeout):
        try:
            if (method != 'POST' or url != self._url or not _positive(timeout) or
                    type(body) is not bytes or len(body) > 1 << 20):
                raise ValueError
            payload = _object(body)
            self._payload(payload)
            allowed = {'openai': {'content-type', 'authorization'},
                       'anthropic': {'content-type', 'x-api-key', 'anthropic-version'},
                       'gemini': {'content-type', 'x-goog-api-key'}}[self._adapter]
            if headers is None:
                headers = {}
            if not isinstance(headers, dict):
                raise ValueError
            seen = set()
            for name, value in headers.items():
                if (not isinstance(name, str) or name.lower() not in allowed or
                        name.lower() in seen or not isinstance(value, str) or
                        len(value) > 16384 or any(ord(c) < 32 or ord(c) == 127 for c in value)):
                    raise ValueError
                seen.add(name.lower())
                if name.lower() == 'content-type' and value != 'application/json':
                    raise ValueError
            if 'content-type' not in seen:
                raise ValueError
            return urllib.request.Request(url, data=body, method=method, headers=headers)
        except (ValueError, TypeError, AttributeError, RecursionError, OverflowError):
            _fail()

    def _payload(self, payload):
        if self._adapter == 'gemini':
            required = {'contents', 'generationConfig'}
            allowed = required | {'systemInstruction'}
            config = payload.get('generationConfig')
            if (not isinstance(config, dict) or
                    not {'temperature', 'maxOutputTokens'} <= config.keys() or
                    config.keys() - {'temperature', 'maxOutputTokens', 'candidateCount'} or
                    not isinstance(payload.get('contents'), list)):
                raise ValueError
            cap, count = config['maxOutputTokens'], config.get('candidateCount', 1)
        else:
            required = {'model', 'messages', 'max_tokens'}
            allowed = required | {'temperature', 'stream'}
            allowed |= {'n'} if self._adapter == 'openai' else {'system'}
            if (payload.get('model') != self._model or
                    not isinstance(payload.get('messages'), list)):
                raise ValueError
            config = payload
            cap, count = payload.get('max_tokens'), payload.get('n', 1)
        if (not required <= payload.keys() or payload.keys() - allowed or
                type(cap) is not int or cap != self._max_tokens or
                type(count) is not int or count != 1 or
                payload.get('stream', False) is not False):
            raise ValueError
        temperature = config.get('temperature')
        if 'temperature' not in config and self._allow_omitted_temperature:
            return
        if type(temperature) not in (int, float) or temperature != 0:
            raise ValueError

    def _stage_timeout(self, timeout):
        remaining = self._remaining()
        self._deadline_limited = remaining <= timeout
        return min(timeout, remaining)

    def _read(self, response, timeout):
        # read1 performs a single buffered read, allowing the deadline to be
        # checked even when the provider dribbles data below a socket timeout.
        chunks, size = [], 0
        while True:
            remaining = self._stage_timeout(timeout)
            sock = getattr(getattr(getattr(response, 'fp', None), 'raw', None), '_sock', None)
            if sock is not None:
                sock.settimeout(remaining)
            chunk = response.read1(min(65536, (2 << 20) + 1 - size))
            self._remaining()
            size += len(chunk)
            if size > 2 << 20:
                _fail('EXTERNAL_ACTION_FAILED')
            if not chunk:
                break
            chunks.append(chunk)
        return _object(b''.join(chunks)) if size else {}

    def __call__(self, method, url, headers, body, timeout):
        request = self._request(method, url, headers, body, timeout)
        remaining = self._stage_timeout(timeout)
        if self._calls >= self._max_calls:
            _fail()
        self._calls += 1
        try:
            try:
                response = self._opener.open(request, timeout=remaining)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                self._remaining()
                status = response.status
                if type(status) is not int or not 200 <= status <= 599 or 300 <= status < 400:
                    _fail('EXTERNAL_ACTION_FAILED')
                return status, self._read(response, timeout)
        except AgentTransportError:
            raise
        except (socket.timeout, TimeoutError):
            if self._deadline_limited:
                _fail('OPERATION_DEADLINE_EXCEEDED')
            self._remaining()
            _fail('EXTERNAL_ACTION_FAILED')
        except urllib.error.URLError as error:
            if isinstance(error.reason, TimeoutError) and self._deadline_limited:
                _fail('OPERATION_DEADLINE_EXCEEDED')
            self._remaining()
            _fail('EXTERNAL_ACTION_FAILED')
        except Exception:
            # Do not expose request URLs, keys, upstream bodies, or exception
            # diagnostics. Malformed responses and transport faults share a code.
            self._remaining()
            _fail('EXTERNAL_ACTION_FAILED')
