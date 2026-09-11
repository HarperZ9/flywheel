"""Frozen lanes must use owned components, never ambient developer installs."""
from pathlib import Path
from types import SimpleNamespace
import json
import os
import subprocess
import sys

import pytest

from harness import bundled_lane_admission as admission
from harness.bundled_lane_expectations import expected_bundled_lane
from harness.lane_runtime import resolve_lane_runtime
from harness.lanes_registry import LANES

ROOT = Path(__file__).resolve().parents[1]


def _resolve(name, *, frozen=True, installed=None):
    return resolve_lane_runtime(
        name, LANES, {}, environ={'FLYWHEEL_HOME': str(ROOT / 'fixture-home')},
        python_executable='C:/fixture/gateway.exe',
        is_frozen=frozen, source_resolver=lambda lane: None,
        extra_roots=lambda lane: [], importable_fn=lambda module: True,
        installed_version_fn=lambda lane: installed,
        package_runtime_version_fn=lambda lane, exe: installed)


@pytest.mark.parametrize('name', ['gather', 'learn'])
def test_auto_missing_package_cannot_report_present(name):
    result = _resolve(name, frozen=False)
    assert result.present is False
    assert 'package_runtime_missing' in result.blocking_codes


@pytest.mark.parametrize('name', ['gather', 'learn'])
def test_frozen_unbundled_lane_never_uses_path_even_with_external_package(name):
    result = _resolve(name, installed=LANES[name].version)
    assert result.present is False
    assert result.launch is None
    assert 'bundled_component_unavailable' in result.blocking_codes


@pytest.mark.parametrize('name', ['writing', 'local-model'])
def test_core_lane_resolves_exact_self_child_and_bounded_tools(name):
    result = _resolve(name)
    assert result.blocking_codes == ()
    assert result.launch.argv == ('C:/fixture/gateway.exe', '--bundled-lane-mcp', name)
    assert result.launch.inherit_env is False
    assert set(result.launch.allowed_tools) == {name + '.status', name + '.doctor'}
    assert result.bundled_component['name'] == name


@pytest.mark.parametrize('name', ['writing', 'local-model'])
def test_core_descriptor_tamper_cannot_choose_another_module(tmp_path, name):
    descriptor = json.loads((ROOT / 'packaging/bundled-lanes' / (name + '.json')).read_text())
    descriptor['entrypoint']['module'] = 'subprocess'
    path = tmp_path / 'descriptor.json'
    path.write_text(json.dumps(descriptor))
    result = admission.admit_bundled_lane(name, executable='C:/fixture/gateway.exe',
        environ={'FLYWHEEL_HOME': str(tmp_path)}, descriptor_path=path,
        importable_fn=lambda module: True)
    assert result.launch is None
    assert 'bundled_descriptor_digest_mismatch' in result.blocking_codes


@pytest.mark.parametrize('args', [
    ['--bundled-lane-mcp', '../writing'],
    ['--bundled-lane-mcp', 'subprocess'],
    ['--bundled-lane-mcp', 'writing', '--module', 'subprocess'],
])
def test_public_child_arguments_cannot_choose_code(args):
    imports = []
    assert admission.dispatch_bundled_lane_mcp(args, import_module_fn=imports.append) == 2
    assert imports == []


@pytest.mark.parametrize('name', ['writing', 'local-model'])
def test_core_child_dispatch_uses_compiled_callable(monkeypatch, name):
    imported = []
    monkeypatch.setattr(admission, '_module_importable', lambda module: True)
    def load(module):
        imported.append(module)
        return SimpleNamespace(serve=lambda: 0)
    result = admission.dispatch_bundled_lane_mcp(
        ['--bundled-lane-mcp', name], import_module_fn=load,
        executable='C:/fixture/gateway.exe',
        environ={'FLYWHEEL_HOME': str(ROOT / 'fixture-home')})
    assert result == 0
    assert imported == [expected_bundled_lane(name)['module']]


@pytest.mark.parametrize('name', ['writing', 'local-model'])
def test_core_source_gate_catches_changed_entrypoint_and_missing_descriptor(tmp_path, name):
    from harness.bundled_lane_core import check_core_descriptor
    assert check_core_descriptor(ROOT, name)['verdict'] == 'PASS'
    (tmp_path / 'harness').mkdir()
    filename = 'writing_mcp.py' if name == 'writing' else 'local_mcp.py'
    (tmp_path / 'harness' / filename).write_text('# replaced\n')
    result = check_core_descriptor(tmp_path, name)
    assert result['verdict'] == 'HOLD'
    assert 'bundled_descriptor_missing' in result['blocking_codes']
    assert 'bundled_source_digest_mismatch' in result['blocking_codes']


@pytest.mark.parametrize('name', ['writing', 'local-model'])
def test_core_missing_import_refuses_even_with_valid_descriptor(name):
    result = admission.admit_bundled_lane(name, executable='C:/fixture/gateway.exe',
        environ={'FLYWHEEL_HOME': str(ROOT / 'fixture-home')},
        importable_fn=lambda module: False)
    assert result.launch is None
    assert result.blocking_codes == ('bundled_module_missing',)


@pytest.mark.parametrize('name', ['writing', 'local-model'])
def test_real_core_stdio_returns_identity_from_isolated_home(tmp_path, name):
    """Real source child/protocol; not a frozen-build or installed-payload test."""
    env = {key: value for key, value in os.environ.items()
           if key.upper() in {'SYSTEMROOT', 'WINDIR', 'PATH', 'COMSPEC', 'PATHEXT'}}
    env.update(HOME=str(tmp_path), USERPROFILE=str(tmp_path),
               FLYWHEEL_HOME=str(tmp_path), PYTHONDONTWRITEBYTECODE='1')
    code = ('from harness.bundled_lane_admission import dispatch_bundled_lane_mcp;'
            'raise SystemExit(dispatch_bundled_lane_mcp(["--bundled-lane-mcp",'
            + repr(name) + ']))')
    requests = [
        {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
        {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}},
        {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
         'params': {'name': name + '.status', 'arguments': {}}},
        {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call',
         'params': {'name': name + '.doctor', 'arguments': {'home': str(tmp_path / 'outside')}}},
    ]
    proc = subprocess.run([sys.executable, '-B', '-c', code],
        cwd=ROOT, env=env, input='\n'.join(map(json.dumps, requests)) + '\n',
        capture_output=True, text=True, timeout=10,
        creationflags=0x08000000 if os.name == 'nt' else 0)
    assert proc.returncode == 0
    raw = {row['id']: row for row in map(json.loads, proc.stdout.splitlines())}
    assert raw[4]['error']['data']['code'] == 'CAPABILITY_NOT_ADMITTED'
    assert not (tmp_path / 'outside').exists()
    replies = {rid: row['result'] for rid, row in raw.items() if 'result' in row}
    assert replies[1]['serverInfo']['version'] == '0.1.0'
    assert {name + '.status', name + '.doctor'} == {tool['name'] for tool in replies[2]['tools']}
    assert all(t['inputSchema']['properties'] == {} for t in replies[2]['tools'])
    status = json.loads(replies[3]['content'][0]['text'])
    if name == 'writing':
        assert status == {'schema': 'flywheel.writing-status/v1', 'projects': []}
        assert not (tmp_path / '.flywheel').exists()
    else:
        assert status['ok'] is True
        assert status['version'] == '0.1.0'


@pytest.mark.parametrize('home', [None, '', 'relative/home'])
def test_writing_never_falls_back_to_parent_profile(home):
    result = admission.admit_bundled_lane('writing', executable='C:/fixture/gateway.exe',
        environ={'FLYWHEEL_HOME': home} if home is not None else {},
        importable_fn=lambda module: True)
    assert result.launch is None
    assert 'bundled_state_root_missing' in result.blocking_codes


def test_writing_child_preserves_only_explicit_state_directory(tmp_path):
    result = admission.admit_bundled_lane('writing', executable='C:/fixture/gateway.exe',
        environ={'FLYWHEEL_HOME': str(tmp_path), 'ANTHROPIC_API_KEY': 'synthetic'},
        importable_fn=lambda module: True)
    assert dict(result.launch.env_overrides)['FLYWHEEL_HOME'] == str(tmp_path)
    assert 'ANTHROPIC_API_KEY' not in dict(result.launch.env_overrides)
