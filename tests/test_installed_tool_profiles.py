"""Installed profile acceptance must bind actual installed bytes before probing."""
import hashlib
import json
from pathlib import Path

import pytest

from harness.lanes_registry import LANES
from harness.tool_mcp import TOOLS
from scripts import check_installed_tool_profiles as subject


@pytest.fixture
def installed(tmp_path, monkeypatch):
    root = tmp_path / 'installation'
    engine = root / 'engine'
    metadata = engine / '_internal/flywheel-metadata'
    metadata.mkdir(parents=True)
    exe = engine / 'flywheel-gateway.exe'
    exe.write_bytes(b'synthetic installed engine')
    identity = metadata / 'flywheel-frozen-source.json'
    identity.write_text(json.dumps({'schema': 'flywheel.frozen-source/v1',
        'head': 'a' * 40, 'version': '1.2.0', 'source_dirty': False}))
    package = engine / '_internal/flywheel_verify.egg-info'
    package.mkdir()
    (package / 'PKG-INFO').write_text('Name: flywheel-verify\nVersion: 1.2.0\n')
    calls = []

    def tool_check(path, version):
        calls.append(('tool', path, version))
        return {'schema': 'flywheel.frozen-tool-mcp/v1', 'status': 'PASS',
            'version': version, 'executable_sha256': hashlib.sha256(exe.read_bytes()).hexdigest(),
            'receipt_fixture_verified': True, 'selected_roots_unchanged': True,
            'private': str(tmp_path)}

    def art_check(path, version, receipt):
        calls.append(('articulate', path, version))
        receipt.update(observed_version=version, tool_names=sorted(subject.articulate.TOOLS),
            local_only=True, host_edit_roundtrip=True, numeric_change_refused=True,
            isolated_runtime_removed=True, backend_refusals=15, sampling_requests=0,
            executable_sha256='sha256:' + hashlib.sha256(exe.read_bytes()).hexdigest(),
            executable=str(path))

    monkeypatch.setattr(subject.tool_mcp, 'check', tool_check)
    monkeypatch.setattr(subject.articulate, 'check', art_check)
    return root, exe, identity, calls


def invoke(installed, tmp_path, **overrides):
    root, exe, _, _ = installed
    args = {'install-root': str(root), 'expected-version': '1.2.0',
            'expected-engine-sha256': hashlib.sha256(exe.read_bytes()).hexdigest(),
            'source-commit': 'a' * 40, 'receipt': str(tmp_path / 'receipt.json')}
    args.update(overrides)
    code = subject.main([part for key, value in args.items() for part in ('--' + key, value)])
    return code, json.loads(Path(args['receipt']).read_text())


def test_installed_only_bound_and_receipt_bounded(installed, tmp_path):
    code, receipt = invoke(installed, tmp_path)
    assert code == 0 and receipt['verdict'] == 'PASS'
    assert installed[3] == [('tool', installed[1], '1.2.0'),
                            ('articulate', installed[1], LANES['articulate'].version)]
    assert receipt['profiles']['tool_mcp']['tool_names'] == sorted(t['name'] for t in TOOLS)
    assert receipt['profiles']['articulate']['version'] == LANES['articulate'].version
    assert str(tmp_path) not in json.dumps(receipt)
    assert receipt['registry_installation_verified'] is False


def test_installed_wheel_metadata_uses_shared_resolution(installed, tmp_path):
    package = installed[1].parent / '_internal/flywheel_verify.egg-info'
    (package / 'PKG-INFO').rename(package / 'METADATA')
    package.rename(package.with_name('flywheel_verify-1.2.0.dist-info'))
    code, receipt = invoke(installed, tmp_path)
    assert code == 0 and receipt['identity_verified_before_after'] is True


@pytest.mark.parametrize('change', ['hash', 'source', 'dirty', 'version', 'package'])
def test_identity_failure_prevents_protocol_probe(installed, tmp_path, change):
    overrides = {}
    if change == 'hash':
        overrides['expected-engine-sha256'] = '0' * 64
    elif change == 'source':
        overrides['source-commit'] = 'b' * 40
    elif change == 'version':
        overrides['expected-version'] = '1.3.0'
    elif change == 'dirty':
        body = json.loads(installed[2].read_text())
        body['source_dirty'] = True
        installed[2].write_text(json.dumps(body))
    else:
        (installed[1].parent / '_internal/flywheel_verify.egg-info/PKG-INFO').write_text(
            'Name: flywheel-verify\nVersion: 99.0.0\n')
    code, receipt = invoke(installed, tmp_path, **overrides)
    assert code == 1 and receipt['verdict'] == 'HOLD'
    assert installed[3] == []


@pytest.mark.parametrize('checker', ['tool_mcp', 'articulate'])
def test_checker_failure_holds_without_private_exception(installed, tmp_path, monkeypatch, checker):
    def fail(*args):
        raise RuntimeError(str(tmp_path) + ' private text')
    monkeypatch.setattr(getattr(subject, checker), 'check', fail)
    code, receipt = invoke(installed, tmp_path)
    assert code == 1 and receipt['verdict'] == 'HOLD'
    assert str(tmp_path) not in json.dumps(receipt)


@pytest.mark.parametrize('checker', ['tool_mcp', 'articulate'])
def test_missing_success_evidence_holds(installed, tmp_path, monkeypatch, checker):
    monkeypatch.setattr(getattr(subject, checker), 'check', lambda *args: {})
    code, receipt = invoke(installed, tmp_path)
    assert code == 1 and receipt['verdict'] == 'HOLD'
    assert 'profiles' not in receipt


def test_engine_mutation_during_probe_holds(installed, tmp_path, monkeypatch):
    original = subject.articulate.check
    def mutate(*args):
        original(*args)
        installed[1].write_bytes(b'changed engine')
    monkeypatch.setattr(subject.articulate, 'check', mutate)
    code, receipt = invoke(installed, tmp_path)
    assert code == 1 and receipt['stage'] == 'final_identity'
    assert 'identity_verified_before_after' not in receipt


def test_ci_order_receipt_and_line_budget():
    root = Path(__file__).resolve().parents[1]
    script = (root / 'desktop/tool/run_ci_installed_acceptance.ps1').read_text()
    assert script.index('"installed Canon context acceptance"') < script.index(
        '"installed tool profile acceptance"') < script.index('"installed lane acceptance"')
    assert 'installed-tool-profiles.json' in script
    assert len(script.splitlines()) <= 300
    workflow = (root / '.github/workflows/windows-installed-acceptance.yml').read_text()
    assert 'installed-acceptance/*.json' in workflow
