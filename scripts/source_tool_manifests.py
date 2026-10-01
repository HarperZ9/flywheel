"""Client metadata for the existing restricted Flywheel tools entrypoint."""
from __future__ import annotations
import json


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode('utf-8')


def manifests(version, *, dev=False):
    description = ('Unpublished development candidate. ' if dev else '') + (
        'Public evidence-task resources and local receipt membership checks. '
        'Requires Python 3.11 or later; no model, network, process or write grants.')
    base = {'name': 'flywheel-tools', 'version': version, 'description': description,
            'author': {'name': 'Zain Dana Harper'}, 'license': 'FSL-1.1-MIT',
            'repository': 'https://github.com/HarperZ9/flywheel'}
    config = {
        'workspace': {'type': 'directory', 'title': 'Workspace folder', 'required': True,
            'description': 'Existing local project folder, separate from receipt state.'},
        'state': {'type': 'directory', 'title': 'Receipt state folder', 'required': True,
            'description': 'Existing local state with an envelopes folder; read-only access.'},
    }
    args = ['-I', '-S', '-B', '${CLAUDE_PLUGIN_ROOT}/server/serve.py',
            '--root', '${user_config.workspace}', '--run-root', '${user_config.state}']
    server = {'type': 'stdio', 'command': 'python3', 'args': args}
    portable_server = {'type': 'stdio', 'command': 'python3', 'args': [
        '-I', '-S', '-B', '${PLUGIN_ROOT}/server/serve.py', '--root',
        'REPLACE_WITH_ABSOLUTE_WORKSPACE', '--run-root', 'REPLACE_WITH_ABSOLUTE_RECEIPT_STATE']}
    interface = {'displayName': 'Flywheel tools', 'shortDescription': 'Check local receipt membership',
                 'developerName': 'Zain Dana Harper', 'category': 'Developer tools',
                 'supportURL': 'https://github.com/HarperZ9/flywheel/issues',
                 'websiteURL': 'https://github.com/HarperZ9/flywheel'}
    return {
        '.claude-plugin/plugin.json': encoded({**base, 'displayName': 'Flywheel tools', 'userConfig': config}),
        '.claude-plugin/marketplace.json': encoded({'name': 'flywheel-tools', 'description': description,
            'owner': base['author'], 'plugins': [{'name': 'flywheel-tools', 'source': './', 'description': description}]}),
        '.mcp.json': encoded({'mcpServers': {'flywheel': server}}),
        'mcp.json': encoded({'mcpServers': {'flywheel': portable_server}}),
        '.codex-mcp.json': encoded({'mcpServers': {'flywheel': portable_server}}),
        'plugin.json': encoded({'$schema': 'https://agent-plugins.org/schemas/1.0.0/plugin.schema.json',
            **base, 'extensions': {'com.openai': {'interface': interface}}}),
        '.codex-plugin/plugin.json': encoded({**base, 'interface': interface,
            'skills': './skills/', 'mcpServers': './.codex-mcp.json'}),
    }
