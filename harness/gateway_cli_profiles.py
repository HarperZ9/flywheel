"""Closed native CLI session profiles; API-native tools are a separate mode."""
from pathlib import Path
from .gateway_operation import GatewayOperationError

MODE = 'native_cli_session'
ENDPOINTS = {'claude-cli', 'codex-cli'}


def session_profile(endpoint, *, allow_write, allow_exec):
    if endpoint not in ENDPOINTS:
        raise GatewayOperationError('AGENT_ENDPOINT_UNSUPPORTED')
    if endpoint == 'claude-cli':
        if allow_exec:
            raise GatewayOperationError('AGENT_CLI_PERMISSION_UNSUPPORTED')
        tools = ['Read', 'Glob', 'Grep'] + (['Edit', 'Write'] if allow_write else [])
        profile, scope = 'claude_restricted_files_v1', 'working_directory_file_tools'
        required = ['--restricted', '--safe-mode', '--strict-mcp-config', '--tools',
                    '--settings', '--no-session-persistence', '--output-format']
    else:
        # Codex's filesystem inspection uses native shell commands. A read-only
        # sandbox is not a promise that no commands execute.
        if not allow_exec:
            raise GatewayOperationError('AGENT_CLI_PERMISSION_UNSUPPORTED')
        tools = ['command_execution'] + (['file_change'] if allow_write else [])
        profile, scope = 'codex_windows_sandbox_v1', 'os_read_scope_workspace_write_only'
        required = ['--ignore-user-config', '--ignore-rules', '--sandbox', '--json',
                    '--ephemeral', '--model', '--cd']
    return {'provider': endpoint, 'profile': profile, 'tools': tools,
        'filesystem_scope': scope, 'auth_mode': 'official_cli_own_auth',
        'required_flags': required,
        'controls': {'timeout_s': 'owned_process_deadline',
            'max_steps': 'native_turn_limit' if endpoint == 'claude-cli' else 'unsupported',
            'max_tokens': 'unsupported', 'seed': 'unsupported'},
        'limitations': ['NO_OS_ADMINISTRATION', 'NO_PROVIDER_RESUME',
            'PROVIDER_POLICY_APPLIES', 'NO_HARD_TOKEN_LIMIT', 'HIDDEN_REASONING_UNAVAILABLE'] + (
                ['NO_HARD_NATIVE_TURN_LIMIT', 'READ_SCOPE_NOT_WORKSPACE_CONFINED',
                 'UNRECOGNIZED_SUMMARY_FIELDS_OMITTED']
                if endpoint == 'codex-cli' else ['CLAUDE_REASONING_NOT_RETAINED'])}


def session_argv(executable, profile, model, root: Path, max_steps):
    if profile['provider'] == 'claude-cli':
        tools = ','.join(profile['tools'])
        return [executable, '-p', '--model', model, '--restricted', '--safe-mode',
            '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
            '--tools', tools, '--allowedTools', tools, '--disallowedTools', 'mcp__*',
            '--permission-mode', 'dontAsk', '--settings', '{"disableAllHooks":true}',
            '--max-turns', str(max_steps), '--no-chrome', '--disable-slash-commands',
            '--no-session-persistence', '--output-format', 'stream-json', '--verbose']
    sandbox = 'workspace-write' if 'file_change' in profile['tools'] else 'read-only'
    return [executable, 'exec', '--model', model, '--cd', str(root),
        '--sandbox', sandbox, '--ignore-user-config', '--ignore-rules', '--ephemeral',
        '--skip-git-repo-check', '--json', '-c', 'approval_policy="never"',
        '-c', 'model_provider="openai"', '-c', 'mcp_servers={}',
        '-c', 'features.apps=false', '-c', 'features.plugins=false',
        '-c', 'features.hooks=false', '-c', 'features.multi_agent=false',
        '-c', 'web_search="disabled"', '-c', 'windows.sandbox="unelevated"',
        '-c', 'allow_login_shell=false', '-c', 'sandbox_workspace_write.network_access=false',
        '-c', 'sandbox_workspace_write.exclude_tmpdir_env_var=true',
        '-c', 'sandbox_workspace_write.exclude_slash_tmp=true', '-']
