"""Frozen native CLI authority inside the existing agent.run grant."""
from pathlib import Path
import re
from .evidence_json import canonical_sha256
from .gateway_operation import GatewayOperationError
from .gateway_agent_workspace import freeze_workspace, validate_workspace
from .gateway_cli_profiles import MODE, ENDPOINTS, session_profile, session_argv
from .gateway_cli_runtime import freeze_runtime, check_configuration_boundary
from .plan_run_snapshot import freeze_json
from .private_artifact_fs import ArtifactIdentity

SCHEMA = 'flywheel.gateway-agent-binding/v3'


def _request(value):
    from .gateway_agent_binding import MODEL_PATTERN
    if (value.get('execution_mode') != MODE or value['endpoint'] not in ENDPOINTS
            or 'tool_protocol' in value or not MODEL_PATTERN.fullmatch(value.get('model', ''))):
        raise GatewayOperationError('AGENT_CLI_PROFILE_UNSUPPORTED')
    if 'max_tokens' in value or 'effort' in value:
        raise GatewayOperationError('AGENT_CLI_BUDGET_UNSUPPORTED')
    if value.get('test_cmd') or value['credential_refs']:
        raise GatewayOperationError('AGENT_CLI_PERMISSION_UNSUPPORTED')
    return session_profile(value['endpoint'], allow_write=value['allow_write'], allow_exec=value['allow_exec'])


def _binding(operation, workspace, runtime):
    value = operation.operation
    profile = _request(value)
    endpoint = value['endpoint']
    argv = session_argv(runtime['executable'], profile, value['model'],
                        Path(workspace['root']), value['max_steps'])
    return {'schema': SCHEMA, 'execution_mode': MODE,
        'operation_sha256': operation.operation_sha256,
        'endpoint': {'name': endpoint, 'adapter': 'native_cli', 'base_url': '', 'slot': '',
            'local': False, 'default_model': '', 'specification_sha256': canonical_sha256(profile)},
        'model': {'requested_model_reference': value['model'], 'model_id': value['model'],
            'selection': 'explicit', 'observation_policy': 'provider_reported', 'profile': None},
        'workspace': workspace, 'budget': {'max_steps': value['max_steps'],
            'max_tokens': None, 'timeout_s': value.get('timeout_s', 300)},
        'capabilities': {'allow_write': value['allow_write'], 'allow_exec': value['allow_exec'], 'allow_mcp': False},
        'cli_session': profile, 'cli_runtime': runtime, 'argv_sha256': canonical_sha256(argv)}


def freeze_cli_binding(operation, workspace_root):
    profile = _request(operation.operation)
    check_configuration_boundary(operation.operation['endpoint'], workspace_root)
    runtime = freeze_runtime(operation.operation['endpoint'], profile)
    workspace = freeze_workspace(operation.operation.get('root'), workspace_root or Path.cwd())
    check_configuration_boundary(operation.operation['endpoint'], Path(workspace['root']))
    # Codex native commands may read the OS sandbox's read scope. A configured
    # root-only policy must not silently become a machine-read grant.
    if operation.operation['endpoint'] == 'codex-cli' and workspace['policy']['mode'] != 'legacy_open':
        raise GatewayOperationError('AGENT_CLI_PERMISSION_UNSUPPORTED')
    binding = _binding(operation, workspace, runtime)
    validate_cli_binding(binding, operation)
    return freeze_json(binding, max_bytes=32768)


def validate_cli_binding(binding, operation):
    try:
        check_configuration_boundary(operation.operation['endpoint'], None)
        runtime = binding['cli_runtime']
        if set(runtime) != {'executable', 'identity', 'version', 'help_sha256',
                            'auth_directory', 'auth_directory_identity'}: raise ValueError
        for key in ('identity', 'help_sha256'):
            if not re.fullmatch('[a-f0-9]{64}', runtime[key]): raise ValueError
        if not re.fullmatch(r'\d+\.\d+\.\d+', runtime['version']): raise ValueError
        if any(not Path(runtime[k]).is_absolute() for k in ('executable', 'auth_directory')): raise ValueError
        ArtifactIdentity.from_json_dict(runtime['auth_directory_identity'])
        validate_workspace(binding['workspace'])
        if (operation.operation['endpoint'] == 'codex-cli'
                and binding['workspace']['policy']['mode'] != 'legacy_open'): raise ValueError
        expected = _binding(operation, binding['workspace'], runtime)
        if freeze_json(expected) != freeze_json(binding): raise ValueError
    except Exception:
        raise GatewayOperationError('AGENT_BINDING_DRIFT') from None


def review_cli_binding(binding):
    return {'schema': 'flywheel.gateway-agent-review/v3',
        'binding_sha256': freeze_json(binding).sha256, 'execution_mode': MODE,
        'endpoint': binding['endpoint']['name'], 'base_url': '', 'model': binding['model'],
        'root': binding['workspace']['root'], 'workspace_policy_sha256': binding['workspace']['policy_sha256'],
        'budget': binding['budget'], 'capabilities': binding['capabilities'],
        'cli_session': {k: v for k, v in binding['cli_session'].items() if k != 'required_flags'} |
                       {'version': binding['cli_runtime']['version']}}
