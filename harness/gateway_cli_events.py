"""Private CLI events: documented visible summaries, never opaque reasoning.

Limit errors are read from the CLI's own fields and never from content: the
`error` field of a Claude API error event, a result event's
`api_error_status`, a rejected `rate_limit_event`, a Codex error or failed
turn event, and the CLI process's own stderr and exit code. A tool result and
the model's answer are content, so a limit named there is not read."""
from .evidence_json import strict_load_json
from .gateway_operation import GatewayOperationError
from .limit_signal import limit_match, provider_limit


def fail(code='AGENT_CLI_PROTOCOL_ERROR'):
    raise GatewayOperationError(code)


class NativeEvents:
    def __init__(self, provider, tools, emit, *, max_steps, budget=None):
        self.provider, self.tools, self.emit = provider, set(tools), emit
        self.max_steps, self.count, self.turns = max_steps, 0, 0
        self.terminal, self.final, self.model = False, '', None
        self.calls, self.call_names, self.messages = set(), {}, set()
        self.omissions = set()
        # The CLI runs its own tools. The budget can only observe each call
        # as it streams past and stop the session, not refuse the call.
        self.budget = budget
        # The limit the CLI last reported and no clean turn has cleared, so
        # one error restated by a second event is counted once.
        self.limited = None

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
        self.call_names[ident] = name
        self._send('cli_tool_call', call_id=ident, tool=name, arguments=arguments)
        if self.budget is not None: self.budget.count_observed('tool_actions')

    def _limit(self, source, found):
        if self.budget is None or found is None: return
        if self.limited is not None and self.limited.kind == found.kind: return
        self.limited = found
        self.budget.observe_limit(source, found)

    def _clean(self):
        self.limited = None
        if self.budget is not None: self.budget.observe_clean_call()

    def _result_limit(self, event):
        """The limit a result event names in its own fields, and a success after one."""
        self._limit('cli_result', provider_limit(status=event.get('api_error_status')))
        success = event.get('is_error') is False and event.get('subtype') == 'success'
        if success and self.limited is not None and self.budget is not None:
            self.budget.record_false_success('cli_result', self.limited)

    def exited(self, returncode, stderr):
        """Read the CLI process's own stderr for a limit error.

        Only an anchored match counts, and on exit 0 it is a false success."""
        found = limit_match(stderr) if type(stderr) is str else None
        if found is None or not found.anchored or self.budget is None: return
        self._limit('cli_stderr', found)
        if returncode == 0: self.budget.record_false_success('cli_stderr', found)

    def _turn(self, message):
        ident = message.get('id')
        if self.budget is None or type(ident) is not str or ident in self.messages: return
        self.messages.add(ident)
        self.budget.count_observed('model_calls')

    def _claude(self, event):
        kind = event['type']
        if kind == 'assistant':
            msg = event.get('message', {})
            if type(msg) is not dict or type(msg.get('content')) is not list: fail()
            model = msg.get('model')
            if type(model) is str and 0 < len(model) <= 160: self.model = model
            self._turn(msg)
            if event.get('error') is None: self._clean()
            else: self._limit('cli_api_error', provider_limit(error_type=event.get('error')))
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
            if self.budget is not None:
                # Tokens and cost arrive once, for the whole session, errored
                # or not: a CLI token or spend limit can mark a session
                # stopped, not interrupt it. The report covers every model
                # call seen so far.
                self.budget.record_usage(event.get('usage'), cost_usd=event.get('total_cost_usd'),
                                         calls=max(1, self.budget.unaccounted_calls()))
            self._result_limit(event)
            if event.get('is_error') is not False or event.get('subtype') != 'success':
                fail('AGENT_CLI_INCOMPLETE')
            if type(event.get('num_turns')) is not int or not 1 <= event['num_turns'] <= self.max_steps:
                fail('AGENT_CLI_INCOMPLETE')
            self.final, self.terminal = event.get('result'), True
        elif kind == 'rate_limit_event':
            info = event.get('rate_limit_info')
            if type(info) is dict and info.get('status') == 'rejected':
                self._limit('cli_rate_limit_event', provider_limit(error_type='rate_limit'))
        elif kind not in {'system', 'stream_event'}: fail()

    def _codex(self, event):
        kind = event['type']
        if kind in {'error', 'turn.failed'}:
            self._codex_error(event)
            fail('AGENT_CLI_INCOMPLETE')
        if kind == 'turn.completed':
            self._clean()
            model = event.get('model')
            if type(model) is str and 0 < len(model) <= 160: self.model = model
            if self.budget is not None:
                # codex exec reports tokens per turn and hides the model
                # calls inside it, so a turn counts as one call at least.
                self.budget.count_observed('model_calls')
                self.budget.record_usage(event.get('usage'))
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

    def _codex_error(self, event):
        """A Codex error or failed turn: its status and type fields, then its message."""
        error = event.get('error') if type(event.get('error')) is dict else event
        found = (provider_limit(status=error.get('status'), error_type=error.get('code'))
                 or provider_limit(error_type=error.get('type')))
        if found is None:
            match = limit_match(error.get('message'))
            found = match if match is not None and match.anchored else None
        self._limit('cli_error_event', found)

    def finish(self):
        if not self.terminal or type(self.final) is not str or not self.final.strip():
            fail('AGENT_CLI_INCOMPLETE')
        return {'final': self.final, 'model_observed': self.model,
            'execution_mode': 'native_cli_session', 'native_tool_calls': len(self.calls),
            'omissions': sorted(self.omissions),
            'steps': [], 'does_not_prove': ['NOT_SEMANTIC_TRUTH', 'NOT_PROVIDER_SESSION_RESUME']}
