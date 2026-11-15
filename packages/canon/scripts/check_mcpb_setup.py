"""Exercise literal MCPB setup substitutions and strict launch booleans."""
import json

from check_client_common import call, run, value


def expanded_args(manifest, **values):
    settings = {key: spec.get('default') for key, spec in manifest['user_config'].items()}
    settings.update(values)
    args = list(manifest['server']['mcp_config']['args'])
    for key, setting in settings.items():
        rendered = json.dumps(setting) if isinstance(setting, (bool, type(None))) else str(setting)
        args = [arg.replace('${user_config.' + key + '}', rendered) for arg in args]
    return args


def check_setup(executable, manifest, env, root, state):
    values = {'context_db': str(state), 'workspace_id': 'synthetic-workspace', 'project_id': 'synthetic-project'}
    for enabled in (False, True):
        args = expanded_args(manifest, **values, context_write=enabled)
        health = value(call(executable, root, env, args, 'canon.context.health'))
        if health.get('context_write') is not enabled:
            raise ValueError('MCPB launch grant differs from setup')
    for malformed in ('', 'yes', 'TRUE', '1', None, '${user_config.context_write}'):
        args = expanded_args(manifest, **values, context_write=malformed)
        result = run(executable, root, env, args)
        if not result.returncode or result.stdout:
            raise ValueError('malformed MCPB boolean accepted')
    return {'status': 'PASS', 'scope': 'expanded required bindings, default/enabled/malformed write setup'}
