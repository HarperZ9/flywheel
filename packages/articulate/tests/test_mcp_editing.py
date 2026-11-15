"""Exercise editor behavior at the JSON-RPC boundary, including duplex sampling."""
import io
import json
import queue
import threading

import pytest

from articulate import local_mcp


def request(method, params=None, rid=1):
    return dict(jsonrpc='2.0', id=rid, method=method, params=params or {})


def call(name, **arguments):
    result = local_mcp.handle(request('tools/call', dict(name=name, arguments=arguments)))['result']
    assert not result.get('isError'), result
    return json.loads(result['content'][0]['text'])


@pytest.fixture(autouse=True)
def no_external(monkeypatch):
    import subprocess
    import urllib.request
    def forbidden(*args, **kwargs):
        pytest.fail('default MCP editing must not access a separate account or endpoint')
    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr(urllib.request, 'urlopen', forbidden)
    monkeypatch.delenv('ARTICULATE_BACKEND', raising=False)
    monkeypatch.delenv('ARTICULATE_LOCAL_ONLY', raising=False)


@pytest.mark.parametrize('goal', ['judge', 'fix', 'polish'])
def test_unadvertised_auto_offers_host_and_none_runs_deterministic(goal):
    result = call(goal, text='We wait — today.')
    assert result['plan_id']
    assert result['backend'] == 'host'
    deterministic = call(goal, text='We wait — today.', backend='none')
    assert deterministic['ok'] is True
    assert deterministic['backend'] == 'none'


def test_explicit_sampling_without_negotiation_returns_host_plan():
    result = call('fix', text='We wait.', backend='sampling')
    assert result['backend'] == 'host'
    assert result['plan_id']


def test_tex_profile_reaches_host_protocol_and_preserves_masks():
    original = r'We measured $x=14$ — today.'
    plan = call('fix', text=original, is_tex=True, profile='procedure')
    assert '$x=14$' not in plan['masked_text']
    accepted = call('edit_submit', text=original,
                    rewrite=plan['masked_text'].replace(' — ', '. '), plan_id=plan['plan_id'])
    assert '$x=14$' in accepted['text']


def test_host_tools_accept_good_rewrite_and_preserve_bad_protected_spans():
    original = 'We tested 14 samples — see https://example.org.'
    plan = call('edit_plan', text=original, profile='procedure')
    good = call('edit_submit', text=original, rewrite=original.replace(' — ', '. '),
                plan_id=plan['plan_id'], model='scripted-host')
    assert good['gate_after'] == 'ok'
    assert good['receipt']['backend'] == 'host'
    assert good['receipt']['model'] == 'scripted-host'
    bad = call('edit_submit', text=original, rewrite='We tested 15 samples.', plan_id=plan['plan_id'])
    assert bad['text'] == original
    assert bad['refused']


class Input:
    def __init__(self):
        self.lines = queue.Queue()
    def __iter__(self):
        while True:
            line = self.lines.get()
            if line is None:
                return
            yield line
    def send(self, value):
        self.lines.put(json.dumps(value) + '\n')


class Output(io.StringIO):
    def __init__(self, source, answer):
        super().__init__()
        self.source, self.answer = source, answer
    def write(self, line):
        count = super().write(line)
        message = json.loads(line)
        if message.get('method') == 'sampling/createMessage':
            # A request arriving while sampling is pending must survive.
            self.source.send(request('tools/call', {'name': 'score', 'arguments': {'text': 'We wait.'}}, 3))
            self.source.send(dict(jsonrpc='2.0', id='unrelated', result={'content': {'type': 'text', 'text': 'Wrong.'}}))
            if self.answer == 'success':
                self.source.send(dict(jsonrpc='2.0', id=message['id'], result={
                    'role': 'assistant', 'content': {'type': 'text', 'text': 'We wait. Today.'}, 'model': 'scripted-sampler'}))
            elif self.answer == 'error':
                self.source.send(dict(jsonrpc='2.0', id=message['id'], error={'code': -1, 'message': 'secret-token-must-not-echo'}))
            elif self.answer == 'malformed':
                self.source.send(dict(jsonrpc='2.0', id=message['id'], result={
                    'role': 'assistant', 'content': {'type': 'image', 'data': 'secret-token-must-not-echo'}, 'model': 'bad'}))
        if message.get('id') == 3 or (message.get('id') == 2 and self.answer == 'none'):
            self.source.lines.put(None)
        return count


@pytest.mark.parametrize('answer', ['success', 'error', 'timeout', 'malformed'])
def test_stdio_sampling_correlates_and_buffers_with_safe_fallback(answer):
    source = Input()
    output = Output(source, answer)
    source.send(request('initialize', {'capabilities': {'sampling': {}}}))
    source.send(request('tools/call', {'name': 'fix', 'arguments': {'text': 'We wait — today.'}}, 2))
    worker = threading.Thread(target=local_mcp.serve, args=(source, output), kwargs={'sampling_timeout': .03}, daemon=True)
    worker.start()
    worker.join(3)
    assert not worker.is_alive(), 'sampling or queued request deadlocked'
    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    sampled = [m for m in messages if m.get('method') == 'sampling/createMessage']
    assert len(sampled) == 1
    assert sampled[0]['params']['includeContext'] == 'none'
    assert sampled[0]['params']['messages'][0]['content']['type'] == 'text'
    assert any(m.get('id') == 3 for m in messages)
    result = json.loads(next(m for m in messages if m.get('id') == 2)['result']['content'][0]['text'])
    if answer == 'success':
        assert result['backend'] == 'sampling'
        assert result['model'] == 'scripted-sampler'
        assert result['text'] == 'We wait. Today.'
    else:
        assert result['backend'] == 'host'
        assert result['plan_id']
        assert result['attempts']
        assert 'secret-token' not in output.getvalue()


def test_sampling_capabilities_are_session_scoped_and_negotiated_once():
    source = Input()
    output = Output(source, 'none')
    source.send(request('initialize', {'capabilities': {}}))
    source.send(request('initialize', {'capabilities': {'sampling': {}}}, 4))
    source.send(request('tools/call', {'name': 'fix', 'arguments': {'text': 'We wait.'}}, 2))
    local_mcp.serve(source, output)
    assert 'sampling/createMessage' not in output.getvalue()
    assert call('fix', text='We wait.')['backend'] == 'host'


@pytest.mark.parametrize('capabilities', [{}, {'sampling': None}, {'sampling': False}])
def test_unadvertised_stdio_never_sends_sampling_request(capabilities):
    lines = [request('initialize', {'capabilities': capabilities}),
             request('tools/call', {'name': 'fix', 'arguments': {'text': 'We wait.'}}, 2)]
    out = io.StringIO()
    local_mcp.serve(io.StringIO('\n'.join(json.dumps(line) for line in lines)), out)
    assert 'sampling/createMessage' not in out.getvalue()
    result = json.loads(json.loads(out.getvalue().splitlines()[-1])['result']['content'][0]['text'])
    assert result['backend'] == 'host'
