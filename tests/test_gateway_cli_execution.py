"""Owned CLI fixture sessions exercise effects, readback and terminal controls."""
import json
import time
from types import SimpleNamespace
import pytest
from harness.gateway_operation import GatewayOperationError


class FixtureProcess:
    def __init__(self, spec, rows, *, effect=None, code=0):
        self.spec, self.rows, self.effect, self.code = spec, rows, effect, code
        self.closed, self.resumed = False, False
    def resume(self):
        self.resumed = True
        if self.effect: self.effect(self.spec)
        return True
    def stdout_snapshot(self):
        return ('\n'.join(json.dumps(row) for row in self.rows) + '\n').encode(), False
    def capture_overflow(self): return False
    def wait(self, timeout_s):
        return SimpleNamespace(returncode=self.code, malformed_output=False,
            timed_out=False, stdout=self.stdout_snapshot()[0].decode(), elapsed_ms=1)
    def close(self): self.closed = True


def test_owned_session_writes_fixture_and_keeps_native_receipts(tmp_path, monkeypatch):
    from harness import gateway_cli_execution as execution
    from harness.gateway_cli_profiles import session_profile
    profile = session_profile('claude-cli', allow_write=True, allow_exec=False)
    binding = {'endpoint': {'name': 'claude-cli'}, 'model': {'model_id': 'exact-model'},
        'budget': {'max_steps': 3}, 'cli_session': profile,
        'cli_runtime': {'executable': 'fixture.exe', 'auth_directory': str(tmp_path)}}
    monkeypatch.setattr(execution, 'verify_runtime', lambda r: None)
    monkeypatch.setattr(execution, 'pin_runtime', lambda r: __import__('contextlib').nullcontext())
    monkeypatch.setattr(execution, 'check_configuration_boundary', lambda *a: None)
    seen, emitted = [], []
    rows = [
        {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'id': 'w',
            'name': 'Write', 'input': {'file_path': 'answer.txt', 'content': '42'}}]}},
        {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 'w', 'content': 'written'}]}},
        {'type': 'result', 'is_error': False, 'subtype': 'success', 'result': 'Created answer.txt', 'num_turns': 1}]
    def launch(argv, **kwargs):
        def effect(spec):
            assert spec['stdin_bytes'] == b'Create answer.txt containing 42'
            assert spec['cwd'] == tmp_path
            (tmp_path / 'answer.txt').write_text('42')
        proc = FixtureProcess(kwargs, rows, effect=effect)
        seen.append((argv, proc))
        return proc
    result = execution.run_cli_session('Create answer.txt containing 42', binding, tmp_path,
        time.monotonic() + 5, emitted.append, launcher=launch)
    assert (tmp_path / 'answer.txt').read_text() == '42'
    assert result['final'] == 'Created answer.txt' and result['model_observed'] is None
    assert seen[0][1].closed and seen[0][1].resumed
    assert 'Create answer' not in ' '.join(seen[0][0])
    assert any(row['type'] == 'cli_tool_result' for row in emitted)


def test_nonzero_with_success_text_cannot_complete(tmp_path, monkeypatch):
    from harness import gateway_cli_execution as execution
    from harness.gateway_cli_profiles import session_profile
    monkeypatch.setattr(execution, 'verify_runtime', lambda r: None)
    monkeypatch.setattr(execution, 'pin_runtime', lambda r: __import__('contextlib').nullcontext())
    monkeypatch.setattr(execution, 'check_configuration_boundary', lambda *a: None)
    binding = {'endpoint': {'name': 'claude-cli'}, 'model': {'model_id': 'exact'},
        'budget': {'max_steps': 3}, 'cli_session': session_profile('claude-cli', allow_write=False, allow_exec=False),
        'cli_runtime': {'executable': 'fixture.exe', 'auth_directory': str(tmp_path)}}
    proc = FixtureProcess({}, [{'type': 'result', 'is_error': False, 'subtype': 'success',
        'result': 'Done', 'num_turns': 1}], code=1)
    with pytest.raises(GatewayOperationError, match='AGENT_CLI_PROCESS_FAILED'):
        execution.run_cli_session('Read', binding, tmp_path, time.monotonic() + 5,
            lambda e: None, launcher=lambda *a, **k: proc)
    assert proc.closed


@pytest.mark.skipif(__import__('os').name != 'nt', reason='production ownership uses Windows jobs')
def test_real_owned_fixture_has_artifact_readback_and_retained_private_trace(tmp_path, monkeypatch):
    import sys
    from harness import gateway_cli_binding, gateway_cli_execution
    from harness.claude_cli_auth import _identity
    from harness.gateway_agent_binding import freeze_agent_binding
    from harness.gateway_agent_execution import run_private_agent
    from harness.gateway_agent_trace import AgentTrace
    from harness.gateway_operation import canonicalize_operation
    from harness.plan_run_snapshot import thaw_json
    from harness.private_artifact_fs import root_identity
    root, auth, state = (tmp_path / n for n in ('workspace', 'own-auth', 'state'))
    for path in (root, auth, state): path.mkdir()
    driver = root / 'fixture.py'
    driver.write_text("""import json, pathlib, sys
assert 'PRIVATE_FIXTURE_TASK' in sys.stdin.read()
pathlib.Path('answer.txt').write_text('42')
print(json.dumps({'type':'assistant','message':{'content':[{'type':'tool_use','id':'w','name':'Write','input':{'file_path':'answer.txt','content':'42'}}]}}), flush=True)
print(json.dumps({'type':'user','message':{'content':[{'type':'tool_result','tool_use_id':'w','content':'written'}]}}), flush=True)
print(json.dumps({'type':'result','subtype':'success','is_error':False,'result':'Created answer.txt','num_turns':1}), flush=True)
""")
    runtime = {'executable': sys.executable, 'identity': _identity(sys.executable, content=True),
        'version': '2.1.251', 'help_sha256': 'a' * 64, 'auth_directory': str(auth),
        'auth_directory_identity': root_identity(auth).to_json_dict()}
    monkeypatch.setattr(gateway_cli_binding, 'freeze_runtime', lambda *a: runtime)
    monkeypatch.setattr(gateway_cli_execution, 'session_argv', lambda *a: [sys.executable, '-u', str(driver)])
    op = {'goal': 'PRIVATE_FIXTURE_TASK', 'endpoint': 'claude-cli', 'model': 'fixture-exact',
        'root': str(root), 'execution_mode': 'native_cli_session', 'max_steps': 2,
        'allow_write': True, 'allow_exec': False, 'stream': True, 'data_refs': [], 'credential_refs': []}
    binding = thaw_json(freeze_agent_binding(canonicalize_operation('agent.run', op), root))
    trace = AgentTrace(state, 'owner_' + 'a'*32, 'jrn_' + 'b'*32, 'op_' + 'c'*32)
    emitted = []
    result = run_private_agent(op, {}, root, trace, None, emitted.append,
        binding=binding, deadline=time.monotonic() + 10)
    assert result['state'] == 'completed'
    assert (root / 'answer.txt').read_text() == '42'
    assert 'PRIVATE_FIXTURE_TASK' not in json.dumps(emitted)
    records = trace.read()
    assert records[-1]['payload']['final'] == 'Created answer.txt'
    assert any(r['kind'] == 'progress' and r['payload']['type'] == 'cli_tool_result' for r in records)


@pytest.mark.skipif(__import__('os').name != 'nt', reason='production ownership uses Windows jobs')
def test_real_fixture_deadline_terminates_descendants(tmp_path, monkeypatch):
    import sys
    from harness import gateway_cli_execution as execution
    from harness.gateway_cli_profiles import session_profile
    from harness.claude_cli_auth import _identity
    from harness.private_artifact_fs import root_identity
    driver = tmp_path / 'wait.py'
    driver.write_text("import subprocess,sys,time\nsubprocess.Popen([sys.executable,'-c',"
        "\"import time,pathlib;time.sleep(2);pathlib.Path('late.txt').write_text('escaped')\"])\ntime.sleep(10)\n")
    runtime = {'executable': sys.executable, 'identity': _identity(sys.executable, content=True),
        'auth_directory': str(tmp_path), 'auth_directory_identity': root_identity(tmp_path).to_json_dict()}
    binding = {'model': {'model_id': 'fixture'}, 'budget': {'max_steps': 2}, 'cli_runtime': runtime,
        'cli_session': session_profile('claude-cli', allow_write=False, allow_exec=False)}
    monkeypatch.setattr(execution, 'session_argv', lambda *a: [sys.executable, '-u', str(driver)])
    with pytest.raises(GatewayOperationError, match='OPERATION_DEADLINE_EXCEEDED'):
        execution.run_cli_session('Wait', binding, tmp_path, time.monotonic() + .6, lambda e: None)
    time.sleep(2)
    assert not (tmp_path / 'late.txt').exists()


@pytest.mark.skipif(__import__('os').name != 'nt', reason='production ownership uses Windows jobs')
def test_private_event_arrives_while_real_fixture_is_still_running(tmp_path, monkeypatch):
    import sys
    from harness import gateway_cli_execution as execution
    from harness.gateway_cli_profiles import session_profile
    from harness.claude_cli_auth import _identity
    from harness.private_artifact_fs import root_identity
    driver = tmp_path / 'stream.py'
    driver.write_text("""import json,pathlib,time
print(json.dumps({'type':'assistant','message':{'content':[{'type':'text','text':'Still running'}]}}),flush=True)
while not pathlib.Path('ack.txt').exists(): time.sleep(.02)
print(json.dumps({'type':'result','is_error':False,'subtype':'success','result':'Acknowledged live event','num_turns':1}),flush=True)
""")
    binding = {'model': {'model_id': 'fixture'}, 'budget': {'max_steps': 2},
        'cli_runtime': {'executable': sys.executable, 'identity': _identity(sys.executable, content=True),
            'auth_directory': str(tmp_path), 'auth_directory_identity': root_identity(tmp_path).to_json_dict()},
        'cli_session': session_profile('claude-cli', allow_write=False, allow_exec=False)}
    monkeypatch.setattr(execution, 'session_argv', lambda *a: [sys.executable, '-u', str(driver)])
    def on_event(event):
        if event['type'] == 'cli_message': (tmp_path / 'ack.txt').write_text('observed before exit')
    result = execution.run_cli_session('Stream', binding, tmp_path, time.monotonic() + 5, on_event)
    assert result['final'] == 'Acknowledged live event'
