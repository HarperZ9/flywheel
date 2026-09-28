"""Runtime probes and directory authority do not consume account material."""
import sys
from types import SimpleNamespace
import pytest
from harness.gateway_operation import GatewayOperationError


@pytest.mark.skipif(__import__('os').name != 'nt', reason='production CLI admission uses Windows jobs')
def test_help_probe_does_not_inherit_private_environment(monkeypatch, tmp_path):
    from harness import gateway_cli_runtime as runtime
    from harness.gateway_cli_profiles import session_profile
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(tmp_path))
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'PRIVATE_CANARY')
    monkeypatch.setattr(runtime, 'resolve_official_cli', lambda **k: {'ok': True, 'path': sys.executable})
    runtime._CACHE.clear()
    profile = session_profile('claude-cli', allow_write=False, allow_exec=False)
    calls = []
    def probe(executable, args, env):
        calls.append(args)
        assert 'ANTHROPIC_API_KEY' not in env and 'CLAUDE_CONFIG_DIR' not in env
        return SimpleNamespace(returncode=0, timed_out=False, malformed_output=False,
            stdout='2.1.251' if args == ['--version'] else ' '.join(profile['required_flags']))
    monkeypatch.setattr(runtime, '_probe', probe)
    frozen = runtime.freeze_runtime('claude-cli', profile)
    assert calls == [['--version'], ['--help']]
    assert frozen['version'] == '2.1.251'
    assert frozen['auth_directory'] == str(tmp_path)


def test_runtime_binary_replacement_is_rejected(tmp_path):
    from harness.gateway_cli_runtime import verify_runtime
    from harness.claude_cli_auth import _identity
    from harness.private_artifact_fs import root_identity
    path = tmp_path / 'fixture.exe'
    path.write_bytes(b'MZ fixture one')
    runtime = {'executable': str(path), 'identity': _identity(str(path), content=True),
        'auth_directory': str(tmp_path), 'auth_directory_identity': root_identity(tmp_path).to_json_dict()}
    verify_runtime(runtime)
    path.write_bytes(b'MZ fixture two')
    with pytest.raises(GatewayOperationError, match='AGENT_BINDING_DRIFT'):
        verify_runtime(runtime)


def test_codex_unbound_project_configuration_is_refused_without_reading_it(tmp_path):
    from harness.gateway_cli_runtime import check_configuration_boundary
    (tmp_path / '.codex').mkdir()
    (tmp_path / '.codex' / 'config.toml').write_text('SECRET_CANARY_NOT_PARSED')
    with pytest.raises(GatewayOperationError, match='AGENT_CLI_PROFILE_UNSUPPORTED'):
        check_configuration_boundary('codex-cli', tmp_path)
