"""The native companion never turns inherited settings into authority."""
import hashlib
import io
import json
from pathlib import Path
import subprocess

import pytest


def request(method, params=None):
    return {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}}


def roots(tmp_path):
    workspace, state = tmp_path / 'workspace', tmp_path / 'state'
    workspace.mkdir()
    state.mkdir()
    return workspace, state


def test_profile_lists_only_offline_tools_and_resources(tmp_path, monkeypatch):
    from harness import tool_mcp
    workspace, state = roots(tmp_path)
    for grant in ('WRITE', 'EXEC', 'ONLINE'):
        monkeypatch.setenv('FLYWHEEL_LOCAL_AGENT_ALLOW_' + grant, '1')
    tools = tool_mcp.handle(request('tools/list'), workspace, state)['result']['tools']
    assert {t['name'] for t in tools} == {'flywheel.tool_status', 'receipt.verify_inclusion'}
    assert all(t['annotations']['openWorldHint'] is False for t in tools)
    resources = tool_mcp.handle(request('resources/list'), workspace, state)['result']['resources']
    assert len(resources) == 2
    for resource in resources:
        reply = tool_mcp.handle(request('resources/read', {'uri': resource['uri']}), workspace, state)
        text = reply['result']['contents'][0]['text']
        assert hashlib.sha256(text.encode()).hexdigest() == resource['sha256']


@pytest.mark.parametrize('tool', ['local_agent_health', 'local_agent_chat', 'local_agent_run',
    'flywheel.context.health', 'flywheel.context.capture', 'flywheel.context.preflight', 'exec'])
def test_unavailable_tools_refuse_before_dispatch(tmp_path, monkeypatch, tool):
    from harness import tool_mcp
    workspace, state = roots(tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail('refused call performed work')
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    result = tool_mcp.handle(request('tools/call', {'name': tool, 'arguments': {
        'online': True, 'allow_exec': True, 'allow_write': True}}), workspace, state)['result']
    assert result['isError'] is True
    assert result['structuredContent']['error']['code'] == 'TOOL_UNAVAILABLE'
    assert list(state.iterdir()) == []


def test_receipt_membership_uses_only_selected_state(tmp_path):
    from harness import tool_mcp
    workspace, state = roots(tmp_path)
    envelopes = state / 'envelopes'
    envelopes.mkdir()
    raw = b'{"synthetic":true}'
    (envelopes / 'a.json').write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    result = tool_mcp.handle(request('tools/call', {'name': 'receipt.verify_inclusion',
                            'arguments': {'leaf': digest}}), workspace, state)['result']
    assert result['structuredContent']['included'] is True
    assert result['structuredContent']['proof']['tree_size'] == 1


def test_roots_are_explicit_existing_disjoint_and_local(tmp_path):
    from harness import tool_mcp
    workspace, state = roots(tmp_path)
    assert tool_mcp.parse_args(['--root', str(workspace), '--run-root', str(state)]) == (workspace, state)
    for args in ([], ['--root', str(workspace)], ['--root', str(workspace), '--root', str(state)],
                 ['--root', str(workspace), '--run-root', str(workspace)],
                 ['--root', '.', '--run-root', str(state)],
                 ['--root', str(workspace), '--run-root', str(state), '--allow-exec']):
        with pytest.raises(ValueError):
            tool_mcp.parse_args(args)


def test_unknown_method_and_resource_escape_refuse(tmp_path):
    from harness import tool_mcp
    workspace, state = roots(tmp_path)
    assert tool_mcp.handle(request('exec'), workspace, state)['error']['code'] == -32601
    assert tool_mcp.handle(request('resources/read', {'uri': 'file:///secret'}), workspace, state)['error']['code'] == -32602


def test_linked_receipt_directory_cannot_escape_state(tmp_path):
    from harness import tool_mcp
    workspace, state = roots(tmp_path)
    external = tmp_path / 'external'; external.mkdir()
    (external / 'private.json').write_text('private fixture')
    try:
        (state / 'envelopes').symlink_to(external, target_is_directory=True)
    except OSError:
        import os
        if os.name != 'nt':
            pytest.skip('symlinks unavailable')
        subprocess.run(['cmd', '/c', 'mklink', '/J', str(state / 'envelopes'), str(external)],
                       check=True, capture_output=True)
    result = tool_mcp.handle(request('tools/call', {'name': 'receipt.verify_inclusion',
        'arguments': {'leaf': 'f' * 64}}), workspace, state)['result']
    assert result['isError'] is True
    assert result['structuredContent']['error']['code'] == 'RECEIPTS_LEDGER_UNAVAILABLE'


def test_mapped_network_root_refuses_before_filesystem_read(tmp_path, monkeypatch):
    from harness import tool_mcp
    monkeypatch.setattr(tool_mcp, 'remote_drive', lambda _: True, raising=False)
    with pytest.raises(ValueError, match='local'):
        tool_mcp.checked_path(tmp_path)


def test_hardlinked_receipt_is_not_read(tmp_path):
    import os
    from harness import tool_mcp
    workspace, state = roots(tmp_path)
    folder = state / 'envelopes'; folder.mkdir()
    external = tmp_path / 'outside.json'; external.write_text('outside fixture')
    os.link(external, folder / 'linked.json')
    with pytest.raises(ValueError, match='regular'):
        tool_mcp.receipt_ledger(state)


def test_fresh_profile_import_and_calls_have_no_network_process_or_write(tmp_path):
    import os
    import sys
    workspace, state = roots(tmp_path)
    code = '''import sys,os,json
sys.dont_write_bytecode=True
sys.path.insert(0,sys.argv[1])
def audit(event,args):
 if event.startswith(('socket.','subprocess.','os.system','os.posix_spawn')):
  raise RuntimeError('forbidden event: '+event)
 if event=='open':
  mode=args[1]; flags=args[2]
  if (isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC)):
   raise RuntimeError('forbidden write')
sys.addaudithook(audit)
from pathlib import Path
from harness import tool_mcp
workspace,state=tool_mcp.parse_args(['--root',sys.argv[2],'--run-root',sys.argv[3]])
requests=[('initialize',{}),('tools/list',{}),('resources/list',{}),('tools/call',{'name':'flywheel.tool_status'}),('tools/call',{'name':'receipt.verify_inclusion','arguments':{'leaf':'f'*64}})]
for method,params in requests:
 reply=tool_mcp.handle({'jsonrpc':'2.0','id':1,'method':method,'params':params},workspace,state)
 assert 'error' not in reply and not reply['result'].get('isError'),reply
print('PASS')
'''
    env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'TMP', 'TEMP'}}
    env.update({'USERPROFILE': str(tmp_path), 'HOME': str(tmp_path)})
    result = subprocess.run([sys.executable, '-I', '-S', '-c', code, str(Path(__file__).resolve().parents[1]),
                             str(workspace), str(state)], env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'PASS'


def test_notifications_are_silent_and_next_ping_still_works(tmp_path):
    from harness import tool_mcp
    workspace, state = roots(tmp_path)
    messages = [
        {'jsonrpc': '2.0', 'method': 'notifications/cancelled', 'params': {'requestId': 9}},
        {'jsonrpc': '2.0', 'method': 'unknown/notification'},
        request('ping')]
    stdout = io.StringIO()
    assert tool_mcp.main(['--root', str(workspace), '--run-root', str(state)],
        io.StringIO(''.join(json.dumps(value) + '\n' for value in messages)), stdout) == 0
    assert json.loads(stdout.getvalue()) == {'jsonrpc': '2.0', 'id': 1, 'result': {}}
