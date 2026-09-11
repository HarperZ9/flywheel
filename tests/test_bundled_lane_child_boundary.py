"""Direct stdio falsifiers: no reliance on the parent MCP client's filters."""
import io
import json
from types import SimpleNamespace

import pytest

from harness import bundled_lane_admission as admission
from harness.lanes_registry import LANES
from harness.plugin_lane_runtime import lane_plugin_row


@pytest.mark.parametrize('name,forbidden', [
    ('writing', 'writing.project_init'), ('local-model', 'local_agent_run')])
def test_child_filters_list_and_denies_nonadmitted_call(monkeypatch, tmp_path, name, forbidden):
    module = __import__('harness.writing_mcp' if name == 'writing' else 'harness.local_mcp', fromlist=['serve'])
    def forbidden_dispatch(_):
        raise AssertionError('nonadmitted call reached raw server')
    monkeypatch.setattr(module, '_call', forbidden_dispatch)
    sink = io.StringIO()
    source = io.StringIO('\n'.join(map(json.dumps, [
        {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'},
        {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
         'params': {'name': forbidden, 'arguments': {}}},
    ])) + '\n')
    monkeypatch.setattr('sys.stdin', source)
    monkeypatch.setattr('sys.stdout', sink)
    monkeypatch.setattr(admission, '_module_importable', lambda _: True)
    assert admission.dispatch_bundled_lane_mcp(['--bundled-lane-mcp', name],
        import_module_fn=lambda _: module, environ={'FLYWHEEL_HOME': str(tmp_path)}) == 0
    rows = {row['id']: row for row in map(json.loads, sink.getvalue().splitlines())}
    assert {t['name'] for t in rows[1]['result']['tools']} == {name+'.status',name+'.doctor'}
    assert rows[2]['error']['data']['code'] == 'CAPABILITY_NOT_ADMITTED'
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('tool', ['writing.status', 'writing.doctor'])
def test_bundled_writing_rejects_home_override_without_outside_effect(monkeypatch,tmp_path,tool):
    from harness import writing_mcp
    outside = tmp_path / 'outside'
    approved = tmp_path / 'approved'
    approved.mkdir()
    source = io.StringIO(json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/call',
        'params':{'name':tool,'arguments':{'home':str(outside)}}})+'\n')
    sink = io.StringIO()
    monkeypatch.setattr('sys.stdin',source)
    monkeypatch.setattr('sys.stdout',sink)
    assert admission.dispatch_bundled_lane_mcp(['--bundled-lane-mcp','writing'],
        import_module_fn=lambda _:writing_mcp,environ={'FLYWHEEL_HOME':str(approved)}) == 0
    reply=json.loads(sink.getvalue())
    assert reply['error']['data']['code']=='CAPABILITY_NOT_ADMITTED'
    assert not outside.exists()
    assert list(approved.iterdir()) == []


@pytest.mark.parametrize('name,present', [('gather',False),('local-model',True)])
def test_plugin_roster_tracks_selected_runtime_not_static_argv(name,present):
    runtime=SimpleNamespace(present=present,selected_runtime='bundled',
        to_dict=lambda:{'launch':{'kind':'stdio','argv':['executable','--bundled-lane-mcp',name]}})
    row=lane_plugin_row(name,LANES[name],lambda _:['python','stale.py'],lambda _:runtime)
    assert row['enabled'] is present
    assert row['command']==[]
    assert row['status']==('bundled_selected' if present else 'unavailable')


def test_child_startup_exception_is_fixed_exit_without_private_output(monkeypatch, tmp_path):
    def fail(_):
        raise RuntimeError('private module path must not escape')
    monkeypatch.setattr(admission, '_module_importable', lambda _: True)
    assert admission.dispatch_bundled_lane_mcp(['--bundled-lane-mcp', 'writing'],
        import_module_fn=fail, environ={'FLYWHEEL_HOME': str(tmp_path)}) == 2
