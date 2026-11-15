"""The release gate's granted workflow, run against the plugin's own launcher.

Relay 0.7.0's release failed at "granted native write failed": the launcher
started clearing ambient hosted-model settings, and the gate still handed its
loopback fixture to the server through CODEX_PROVIDER_BASE_URL in the
environment. The run found no backend and wrote nothing. The native build runs
only in the release workflow, so ordinary CI never saw it.

These tests run the same gate through ``python serve.py`` on every CI platform,
so a change to how the launcher reads its settings fails here first.
"""
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SERVE = ROOT / 'client-plugin/server/serve.py'


def load(name):
    spec = importlib.util.spec_from_file_location(f'relay_gate_{name}', ROOT / f'scripts/{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def gate(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    return load('check_native_workflow')


def launcher_env(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith(('RELAY_', 'CODEX_'))}
    env.update({k: str(tmp_path) for k in ('HOME', 'USERPROFILE', 'LOCALAPPDATA', 'APPDATA')})
    return env


def test_gate_passes_through_the_launcher_with_explicit_flags(gate, tmp_path):
    receipt = gate.check_workflow([sys.executable, SERVE], tmp_path, launcher_env(tmp_path))
    assert receipt['status'] == 'PASS'
    assert (tmp_path / 'workflow/written.txt').read_text() == 'synthetic persistence'


def test_gate_passes_with_the_manifest_settings_a_user_fills_in(gate, tmp_path):
    from build_client_package import manifests
    from check_mcpb_setup import expanded_args
    manifest = json.loads(manifests('0.0.0', True)['manifest.json'])
    hosted = lambda url: {'api_provider': 'codex', 'api_base_url': url, 'api_model': 'synthetic-fixture'}
    setup = lambda url: {key: expanded_args(manifest, **{key: True}, **hosted(url)) for key in ('write', 'exec')}
    receipt = gate.check_workflow([sys.executable, SERVE], tmp_path, launcher_env(tmp_path), setup)
    assert receipt['status'] == 'PASS'


def test_ambient_gateway_alone_does_not_reach_the_server(gate, tmp_path):
    """The 0.7.0 failure, kept as a control: with the hosted settings left empty,
    the ambient gateway is cleared, no backend exists and the write gate fails
    with the server's own reason."""
    empty = {'write': ['--allow-write', '--api-provider='], 'exec': ['--allow-exec', '--api-provider=']}
    with pytest.raises(ValueError, match='granted native write failed: UNSUPPORTED_BACKEND'):
        gate.check_workflow([sys.executable, SERVE], tmp_path, launcher_env(tmp_path), empty)
