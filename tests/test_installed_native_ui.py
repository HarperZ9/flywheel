"""Native UI acceptance fails closed and never adopts unrelated processes."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from desktop.tool import installed_native_close as probe


def test_profile_drops_credentials_and_redirects_all_homes(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'private')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'private')
    monkeypatch.setenv('FLYWHEEL_LOCAL_AGENT_ALLOW_ONLINE', '1')
    env = probe.profile_env(tmp_path)
    assert 'OPENAI_API_KEY' not in env and 'ANTHROPIC_API_KEY' not in env
    assert env['FLYWHEEL_LOCAL_AGENT_ALLOW_ONLINE'] == '0'
    for key in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'FLYWHEEL_HOME', 'TEMP', 'TMP'):
        assert Path(env[key]).is_relative_to(tmp_path)
    assert env['PATH'].endswith('System32')


class Job:
    pid = 41
    def __init__(self, active=(), cleanup='PASS'):
        self.active = list(active)
        self.cleanup = cleanup
        self.cleaned = False
        self.kernel = SimpleNamespace(WaitForSingleObject=lambda *args: 0)
        self.process = SimpleNamespace(hProcess=1)
    def active_pids(self):
        return self.active, ''
    def terminate_and_verify(self, **kwargs):
        self.cleaned = True
        return {'state': self.cleanup}
    def close(self):
        return True


@pytest.fixture
def setup(tmp_path, monkeypatch):
    job = Job()
    def launch(*args, **kwargs):
        assert kwargs == {'show_window': True}
        return job, ''
    monkeypatch.setattr(probe, 'start_windows_job_process', launch)
    monkeypatch.setattr(probe.native, '_port_listener_rows', lambda port: [])
    monkeypatch.setattr(probe.native, '_wait_for_window', lambda *args: 12)
    monkeypatch.setattr(probe.native, '_wait_for_owned_gateway', lambda *args: ([{'pid': 42}], []))
    monkeypatch.setattr(probe, 'post_close', lambda hwnd: True)
    monkeypatch.setattr(probe, 'clean_exit', lambda job: True)
    monkeypatch.setattr(probe, 'wait_empty', lambda process, timeout: not process.active)
    return job, tmp_path


def test_normal_close_passes_without_forced_cleanup(setup):
    job, root = setup
    result = probe.run(root, root / 'isolated')
    assert result['verdict'] == 'PASS' and result['owned_job_empty'] is True
    assert job.cleaned is False


@pytest.mark.parametrize('failure', ['window', 'gateway', 'post', 'survivor', 'exception', 'crash'])
def test_failure_never_passes_and_always_cleans_owned_job(setup, monkeypatch, failure):
    job, root = setup
    if failure == 'window':
        monkeypatch.setattr(probe.native, '_wait_for_window', lambda *args: None)
    elif failure == 'gateway':
        monkeypatch.setattr(probe.native, '_wait_for_owned_gateway', lambda *args: ([], []))
    elif failure == 'post':
        monkeypatch.setattr(probe, 'post_close', lambda hwnd: False)
    elif failure == 'survivor':
        job.active = [42]
    elif failure == 'crash':
        monkeypatch.setattr(probe, 'clean_exit', lambda process: False)
    else:
        def crash(*args):
            raise RuntimeError('private path or body')
        monkeypatch.setattr(probe.native, '_wait_for_window', crash)
    result = probe.run(root, root / 'isolated')
    assert result['verdict'] == 'HOLD' and job.cleaned
    assert 'private path' not in str(result)


def test_existing_gateway_is_never_launched_or_killed(setup, monkeypatch):
    job, root = setup
    monkeypatch.setattr(probe.native, '_port_listener_rows', lambda port: [{'pid': 99}])
    monkeypatch.setattr(probe, 'start_windows_job_process', lambda *args: pytest.fail('must not launch'))
    result = probe.run(root, root / 'isolated')
    assert result['verdict'] == 'HOLD' and not job.cleaned


def test_ci_gate_precedes_uninstall_and_stays_bounded():
    root = Path(__file__).resolve().parents[1]
    text = (root / 'desktop/tool/run_ci_installed_acceptance.ps1').read_text()
    assert text.index('"installed native UI acceptance"') < text.index('"installed lane acceptance"')
    assert len(text.splitlines()) <= 300


def test_operator_host_refused_before_any_launch(tmp_path, monkeypatch):
    import json
    from scripts import check_installed_native_ui as gate
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
    monkeypatch.setattr(probe, 'run', lambda *args: pytest.fail('operator host launch'))
    receipt = tmp_path / 'receipt.json'
    code = gate.main(['--install-root', str(tmp_path), '--expected-app-sha256', 'a' * 64,
        '--expected-engine-sha256', 'b' * 64, '--expected-version', '1.2.0',
        '--source-commit', 'c' * 40, '--receipt', str(receipt)])
    result = json.loads(receipt.read_text())
    assert code == 1 and result['stage'] == 'host'
    assert str(tmp_path) not in receipt.read_text()


def test_firewall_cleans_only_its_own_rules_even_if_probe_fails(tmp_path, monkeypatch):
    from scripts import check_installed_native_ui as gate
    (tmp_path / 'app.exe').write_bytes(b'fixture')
    commands = []
    monkeypatch.setattr(gate, '_run_powershell', lambda command: commands.append(command))
    with pytest.raises(RuntimeError):
        with gate.block_external_network(tmp_path):
            raise RuntimeError('probe failed')
    assert 'Get-NetFirewallProfile' in commands[0]
    assert '-Program' in commands[1] and '-Action Block' in commands[1]
    assert 'Remove-NetFirewallRule' in commands[-1]
    group = commands[1].split('-Group ')[1].split(' -Direction')[0]
    assert group in commands[-1]
    assert 'Stop-Process' not in ''.join(commands)


def test_firewall_failure_never_enters_probe(tmp_path, monkeypatch):
    from scripts import check_installed_native_ui as gate
    (tmp_path / 'app.exe').write_bytes(b'fixture')
    def fail(command):
        if 'New-NetFirewallRule' in command:
            raise RuntimeError('rule installation failed')
    monkeypatch.setattr(gate, '_run_powershell', fail)
    with pytest.raises(RuntimeError):
        with gate.block_external_network(tmp_path):
            pytest.fail('must not launch without firewall')


@pytest.mark.parametrize('show,expected', [(False, 0), (True, 5)])
def test_windows_startup_visibility_is_opt_in(tmp_path, show, expected):
    import os
    if os.name != 'nt':
        pytest.skip('Windows stream handle startup only')
    from desktop.tool.installed_launch_acceptance_jobs import _startup, STARTF_USESHOWWINDOW
    startup, streams = _startup(tmp_path / 'stdout', tmp_path / 'stderr', show_window=show)
    try:
        assert startup.dwFlags & STARTF_USESHOWWINDOW
        assert startup.wShowWindow == expected
    finally:
        for stream in streams:
            stream.close()
