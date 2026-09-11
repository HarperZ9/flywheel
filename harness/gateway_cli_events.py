"""Private CLI events: documented visible summaries, never opaque reasoning."""
from .evidence_json import strict_load_json
from .gateway_operation import GatewayOperationError


def fail(code='AGENT_CLI_PROTOCOL_ERROR'):
    raise GatewayOperationError(code)


class NativeEvents:
    def __init__(self, provider, tools, emit, *, max_steps):
        self.provider, self.tools, self.emit = provider, set(tools), emit
        self.max_steps, self.count, self.turns = max_steps, 0, 0
        self.terminal, self.final, self.model = False, '', None
        self.calls = set()
        self.omissions = set()

    def feed(self, line):
        if not line.strip(): return
        self.count += 1
        if self.count > 512 or len(line.encode('utf-8')) > 65536: fail()
        try: event = strict_load_json(line.encode('utf-8'), max_bytes=65536, max_depth=16)
        except Exception: fail()
        if type(event) is not dict or type(event.get('type')) is not str: fail()
        if self.terminal: fail()
        if self.provider == 'claude-cli': self._claude(event)
        else: self._codex(event)

    def _send(self, kind, **payload):
        self.emit({'type': kind, 'source': self.provider, **payload})

    def _omit(self, reason):
        if reason not in self.omissions:
            self.omissions.add(reason)
            self._send('cli_omission', reason=reason)

    def _tool(self, ident, name, arguments):
        if name not in self.tools: fail('AGENT_CLI_PERMISSION_UNSUPPORTED')
        if type(ident) is not str or not ident or ident in self.calls: fail()
        self.calls.add(ident)
        self._send('cli_tool_call', call_id=ident, tool=name, arguments=arguments)

    def _claude(self, event):
        kind = event['type']
        if kind == 'assistant':
            msg = event.get('message', {})
            if type(msg) is not dict or type(msg.get('content')) is not list: fail()
            model = msg.get('model')
            if type(model) is str and 0 < len(model) <= 160: self.model = model
            for block in msg['content']:
                if type(block) is not dict: fail()
                if block.get('type') == 'tool_use':
                    self._tool(block.get('id'), block.get('name'), block.get('input'))
                elif block.get('type') == 'text':
                    if type(block.get('text')) is not str: fail()
                    self._send('cli_message', text=block['text'])
                elif block.get('type') in {'thinking', 'redacted_thinking'}:
                    self._omit('PROVIDER_REASONING_NOT_RETAINED')
                # Signatures and opaque continuation never enter trace.
        elif kind == 'user':
            msg = event.get('message', {})
            if type(msg) is not dict: fail()
            for block in msg.get('content', []):
                if type(block) is dict and block.get('type') == 'tool_result':
                    if block.get('tool_use_id') not in self.calls: fail()
                    self._send('cli_tool_result', call_id=block['tool_use_id'],
                        content=block.get('content'), is_error=block.get('is_error', False))
        elif kind == 'result':
            if event.get('is_error') is not False or event.get('subtype') != 'success':
                fail('AGENT_CLI_INCOMPLETE')
            if type(event.get('num_turns')) is not int or not 1 <= event['num_turns'] <= self.max_steps:
                fail('AGENT_CLI_INCOMPLETE')
            self.final, self.terminal = event.get('result'), True
        elif kind not in {'system', 'stream_event', 'rate_limit_event'}: fail()

    def _codex(self, event):
        kind = event['type']
        if kind in {'error', 'turn.failed'}: fail('AGENT_CLI_INCOMPLETE')
        if kind == 'turn.completed':
            model = event.get('model')
            if type(model) is str and 0 < len(model) <= 160: self.model = model
            self.terminal = True
        elif kind in {'item.started', 'item.completed', 'item.updated'}:
            item = event.get('item')
            if type(item) is not dict: fail()
            typ, ident = item.get('type'), item.get('id')
            if typ == 'agent_message' and kind == 'item.completed':
                self.final = item.get('text')
                if type(self.final) is not str: fail()
                self._send('cli_message', text=self.final)
            elif typ in {'command_execution', 'file_change', 'mcp_tool_call', 'web_search'}:
                if typ not in self.tools: fail('AGENT_CLI_PERMISSION_UNSUPPORTED')
                if ident not in self.calls:
                    self._tool(ident, typ, {key: item[key] for key in ('command', 'changes') if key in item})
                if kind == 'item.completed':
                    self._send('cli_tool_result', call_id=ident, content={key: item[key]
                        for key in ('aggregated_output', 'exit_code', 'status', 'changes') if key in item})
            elif typ == 'reasoning' and kind == 'item.completed':
                # Codex exec_events::ReasoningItem documents text as a summary.
                # No other fields are mined or decoded for reasoning content.
                if type(item.get('text')) is str and type(ident) is str:
                    self._send('cli_reasoning_summary', item_id=ident, text=item['text'])
                else:
                    self._omit('PROVIDER_SUMMARY_SHAPE_UNSUPPORTED')
            elif typ not in {'reasoning', 'todo_list', 'agent_message'}: fail()
        elif kind not in {'thread.started', 'turn.started'}: fail()

    def finish(self):
        if not self.terminal or type(self.final) is not str or not self.final.strip():
            fail('AGENT_CLI_INCOMPLETE')
        return {'final': self.final, 'model_observed': self.model,
            'execution_mode': 'native_cli_session', 'native_tool_calls': len(self.calls),
            'omissions': sorted(self.omissions),
            'steps': [], 'does_not_prove': ['NOT_SEMANTIC_TRUTH', 'NOT_PROVIDER_SESSION_RESUME']}
