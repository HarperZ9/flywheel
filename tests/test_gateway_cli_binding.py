"""Exact operation, runtime and own-auth directory admission controls."""
import copy
from pathlib import Path
import pytest
from harness.gateway_operation import canonicalize_operation, GatewayOperationError
from harness.plan_run_snapshot import thaw_json


def operation(root, **extra):
    return {'goal': 'Read fixture.txt', 'endpoint': 'claude-cli', 'model': 'exact-model',
        'root': str(root), 'max_steps': 4, 'allow_write': False, 'allow_exec': False,
        'stream': True, 'data_refs': [], 'credential_refs': [],
        'execution_mode': 'native_cli_session', **extra}


def test_binding_preserves_requested_model_and_refuses_unsupported_budget(tmp_path, monkeypatch):
    from harness import gateway_cli_binding as cli
    from harness.gateway_agent_binding import freeze_agent_binding, validate_agent_binding
    from harness.private_artifact_fs import root_identity
    fake = {'executable': str(tmp_path / 'claude.exe'), 'identity': 'a' * 64,
        'version': '2.1.251', 'help_sha256': 'b' * 64,
        'auth_directory': str(tmp_path), 'auth_directory_identity': root_identity(tmp_path).to_json_dict()}
    monkeypatch.setattr(cli, 'freeze_runtime', lambda *a: fake)
    op = canonicalize_operation('agent.run', operation(tmp_path))
    binding = thaw_json(freeze_agent_binding(op, tmp_path))
    assert binding['model']['model_id'] == 'exact-model'
    assert binding['execution_mode'] == 'native_cli_session'
    assert binding['budget']['max_tokens'] is None
    validate_agent_binding(binding, op)
    changed = copy.deepcopy(binding)
    changed['model']['model_id'] = 'substitute'
    with pytest.raises(GatewayOperationError, match='AGENT_BINDING_DRIFT'):
        validate_agent_binding(changed, op)
    with pytest.raises(GatewayOperationError, match='AGENT_CLI_BUDGET_UNSUPPORTED'):
        freeze_agent_binding(canonicalize_operation('agent.run', operation(tmp_path, max_tokens=1024)), tmp_path)


def test_cli_mode_cannot_be_combined_with_api_native_protocol(tmp_path):
    with pytest.raises(GatewayOperationError):
        canonicalize_operation('agent.run', operation(tmp_path, tool_protocol='native'))


def test_environment_has_only_explicit_own_auth_directory(tmp_path, monkeypatch):
    from harness.gateway_cli_runtime import session_env
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'private-canary')
    monkeypatch.setenv('UNRELATED_SETTING', 'private-canary')
    monkeypatch.setenv('HOME', str(tmp_path / 'synthetic'))
    env = session_env('claude-cli', str(tmp_path / 'own-cli'), tmp_path / 'synthetic')
    assert env['CLAUDE_CONFIG_DIR'] == str(tmp_path / 'own-cli')
    assert env['HOME'] == str(tmp_path / 'synthetic')
    assert 'ANTHROPIC_API_KEY' not in env and 'UNRELATED_SETTING' not in env


@pytest.mark.parametrize('name', ['claude-read', 'claude-write', 'codex-read', 'codex-write'])
def test_paired_review_fixtures_are_derived_from_exact_binding(name):
    import json
    from harness.gateway_cli_binding import review_cli_binding, _binding
    folder = Path(__file__).parent / 'fixtures' / 'native_cli_session'
    binding = json.loads((folder / (name + '-binding.json')).read_text())
    review = json.loads((folder / (name + '-review.json')).read_text())
    op = json.loads((folder / (name + '-operation.json')).read_text())
    assert review == review_cli_binding(binding)
    canonical = canonicalize_operation('agent.run', op)
    assert binding['operation_sha256'] == canonical.operation_sha256
    assert binding == _binding(canonical, binding['workspace'], binding['cli_runtime'])
    assert review['budget']['max_tokens'] is None
    assert not {'cli_runtime', 'argv_sha256'} & review.keys()
