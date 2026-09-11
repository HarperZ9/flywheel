"""Child-side MCP admission for fixed no-argument component checks.

Normal module servers remain unchanged. This guard is installed only around
the compiled bundled child entrypoint, independently of parent-client filters.
"""
from contextlib import contextmanager
import json
import sys

from .evidence_json import strict_load_json

MAX_LINE = 262144


class _Output:
    def __init__(self, stream, allowed, lists):
        self.stream, self.allowed, self.lists = stream, allowed, lists
        self.pending = ''

    def write(self, text):
        self.pending += text
        if len(self.pending) > MAX_LINE:
            raise ValueError('bundled_output_limit')
        while '\n' in self.pending:
            line, self.pending = self.pending.split('\n', 1)
            if not line.strip():
                continue
            value = strict_load_json(line.encode(), max_bytes=MAX_LINE)
            if not isinstance(value, dict):
                raise ValueError('bundled_output_invalid')
            if value.get('id') in self.lists and 'result' in value:
                self.lists.discard(value['id'])
                tools = value['result'].get('tools', [])
                value['result'] = {'tools': [
                    {**tool, 'inputSchema': {'type': 'object', 'properties': {},
                                            'additionalProperties': False}}
                    for tool in tools if isinstance(tool, dict)
                    and tool.get('name') in self.allowed]}
            self.stream.write(json.dumps(value) + '\n')
        return len(text)

    def flush(self):
        self.stream.flush()


class _Input:
    def __init__(self, stream, output, allowed, lists):
        self.stream, self.output = stream, output
        self.allowed, self.lists = allowed, lists

    def __iter__(self):
        return self

    def __next__(self):
        line = self.readline()
        if not line:
            raise StopIteration
        return line

    def readline(self, size=-1):
        while True:
            line = self.stream.readline(MAX_LINE + 1)
            if not line:
                return ''
            if len(line) > MAX_LINE:
                raise ValueError('bundled_input_limit')
            if not line.strip():
                continue
            try:
                req = strict_load_json(line.encode(), max_bytes=MAX_LINE)
                if not isinstance(req, dict) or req.get('jsonrpc') != '2.0':
                    raise ValueError
                rid, method = req.get('id'), req.get('method')
                if type(rid) not in (str, int, type(None)):
                    raise ValueError
                params = req.get('params', {})
                permitted = method in ('initialize', 'notifications/initialized', 'ping', 'tools/list')
                if method == 'tools/call' and isinstance(params, dict):
                    permitted = (params.get('name') in self.allowed
                                 and params.get('arguments', {}) == {})
                if permitted:
                    if method == 'tools/list':
                        self.lists.add(rid)
                    return line
            except (ValueError, TypeError):
                rid = None
            if rid is not None:
                self.output.write(json.dumps({'jsonrpc': '2.0', 'id': rid,
                    'error': {'code': -32602, 'message': 'lane capability is not admitted',
                              'data': {'code': 'CAPABILITY_NOT_ADMITTED'}}}) + '\n')
                self.output.flush()


@contextmanager
def admitted_stdio(allowed_tools):
    old_in, old_out = sys.stdin, sys.stdout
    lists, allowed = set(), frozenset(allowed_tools)
    output = _Output(old_out, allowed, lists)
    sys.stdin, sys.stdout = _Input(old_in, output, allowed, lists), output
    try:
        yield
        if output.pending:
            raise ValueError('bundled_output_incomplete')
    finally:
        sys.stdin, sys.stdout = old_in, old_out
