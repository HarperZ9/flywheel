"""Bounded HTTP ingress and request-scoped logging for the opt-in service."""
import asyncio
from collections import deque
from contextvars import ContextVar
import json
import logging
import time


_hosted_request = ContextVar('articulate_hosted_request', default=False)


def install_log_redaction():
    """Redact Python log messages only inside hosted request contexts.

    Installing once composes with the existing record factory. Worker threads
    inherit context through FastMCP/AnyIO. Unrelated application logs keep their
    normal contents. Custom sinks which bypass Python logging are outside this
    boundary and must not be enabled by a deployment.
    """
    previous = logging.getLogRecordFactory()
    if getattr(previous, '_articulate_hosted', False):
        return

    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        if _hosted_request.get():
            record.msg = 'Hosted request event (details omitted).'
            record.args = ()
            record.exc_info = record.exc_text = record.stack_info = None
        return record

    factory._articulate_hosted = True
    logging.setLogRecordFactory(factory)


def valid_call(message, config):
    """Reject unsupported input before SDK validation can echo its values."""
    if not isinstance(message, dict) or message.get('jsonrpc') != '2.0':
        return False
    method = message.get('method')
    if method not in {'initialize', 'ping', 'tools/list', 'tools/call',
                      'notifications/initialized', 'notifications/cancelled'}:
        return False
    if method != 'tools/call':
        return True
    params = message.get('params')
    if not isinstance(params, dict) or set(params) - {'name', 'arguments', '_meta'}:
        return False
    name = params.get('name')
    allowed = {
        'check': {'text', 'max_hits'}, 'score': {'text'},
        'edit_plan': {'text', 'mode', 'profile', 'goal', 'is_html', 'is_tex'},
        'edit_submit': {'text', 'rewrite', 'plan_id', 'scores', 'model'},
    }
    if not isinstance(name, str) or name not in allowed:
        return False
    args = params.get('arguments', {})
    if not isinstance(args, dict) or set(args) - allowed[name]:
        return False
    required = {'text', 'rewrite', 'plan_id'} if name == 'edit_submit' else {'text'}
    if not required <= set(args):
        return False
    for key, value in args.items():
        if key in {'text', 'rewrite', 'plan_id'}:
            limit = config.max_plan_chars if key == 'plan_id' else config.max_chars
            if not isinstance(value, str) or len(value) > limit:
                return False
        elif key in {'mode', 'profile', 'goal', 'model'}:
            if value is not None and (not isinstance(value, str) or len(value) > 128):
                return False
            if key == 'goal' and value not in {'fix', 'polish', 'judge'}:
                return False
        elif key in {'is_html', 'is_tex'}:
            if type(value) is not bool:
                return False
        elif key == 'max_hits':
            if value is not None and (type(value) is not int or not 0 <= value <= 1000):
                return False
        elif key == 'scores' and value is not None:
            from .prompts import QUALITIES
            if not isinstance(value, dict) or set(value) != {'before', 'after'}:
                return False
            for assessment in value.values():
                if not isinstance(assessment, dict) or set(assessment) != set(QUALITIES):
                    return False
                if any(type(n) is not int or not 1 <= n <= 5 for n in assessment.values()):
                    return False
    return True


class HostedBoundary:
    """One-process ingress budget; no identity, content, or token storage."""
    def __init__(self, app, config):
        self.app, self.config = app, config
        self.active = 0
        self.requests = deque()
        self.lifespan = app.lifespan

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        marker = _hosted_request.set(True)
        async def no_store(message):
            if message['type'] == 'http.response.start':
                message = dict(message)
                message['headers'] = [(k, v) for k, v in message.get('headers', [])
                                      if k.lower() != b'cache-control']
                message['headers'].append((b'cache-control', b'no-store'))
            await send(message)
        try:
            await self._http(scope, receive, no_store)
        finally:
            _hosted_request.reset(marker)

    async def _http(self, scope, receive, send):
        async def reject(status):
            headers = [(b'content-type', b'application/json'), (b'cache-control', b'no-store')]
            if status == 429:
                headers.append((b'retry-after', b'60'))
            await send({'type': 'http.response.start', 'status': status, 'headers': headers})
            await send({'type': 'http.response.body', 'body': b'{"error":"Request rejected"}'})

        now = time.monotonic()
        while self.requests and self.requests[0] <= now - 60:
            self.requests.popleft()
        if len(self.requests) >= self.config.requests_per_minute or self.active >= self.config.max_concurrent:
            return await reject(429)
        self.requests.append(now)
        self.active += 1
        try:
            # Stateless JSON responses do not need an open SSE listener.
            if scope['path'].rstrip('/') == '/mcp' and scope['method'] != 'POST':
                return await reject(405)
            if scope['method'] == 'POST':
                headers = dict(scope['headers'])
                if headers.get(b'content-encoding', b'identity').lower() != b'identity':
                    return await reject(415)
                try:
                    length = int(headers.get(b'content-length', b'0'))
                except ValueError:
                    return await reject(400)
                if length < 0 or length > self.config.max_body_bytes:
                    return await reject(413)
                body = bytearray()

                async def read_body():
                    while True:
                        message = await receive()
                        if message['type'] == 'http.disconnect':
                            return False
                        body.extend(message.get('body', b''))
                        if len(body) > self.config.max_body_bytes:
                            return False
                        if not message.get('more_body', False):
                            return True

                try:
                    complete = await asyncio.wait_for(read_body(), self.config.read_timeout)
                except asyncio.TimeoutError:
                    return await reject(408)
                if not complete:
                    return await reject(413)
                try:
                    message = json.loads(body)
                    valid = valid_call(message, self.config)
                except (ValueError, TypeError, RecursionError):
                    valid = False
                if not valid:
                    return await reject(400)

                delivered = False

                async def replay():
                    nonlocal delivered
                    if not delivered:
                        delivered = True
                        return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
                    return await receive()

                await self.app(scope, replay, send)
            else:
                await self.app(scope, receive, send)
        finally:
            self.active -= 1
