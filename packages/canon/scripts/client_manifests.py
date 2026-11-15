"""Client manifests share one explicit binding and permission contract."""
import json


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def bindings(prefix):
    names = ('context_db', 'workspace_id', 'project_id')
    return [item for name in names for item in (
        '--' + name.replace('_', '-'), '${' + prefix + name + '}')]


SITE = 'https://harperz9.github.io'
REPOSITORY = 'https://github.com/HarperZ9/canon'
ICON = './.claude-plugin/icon.png'
SETTINGS = (('context_db', 'Canon context database',
             'Absolute path of the SQLite context database. Its parent folder must exist.'),
            ('workspace_id', 'Workspace ID', 'Every request stays bound to this workspace ID.'),
            ('project_id', 'Project ID', 'Every request stays bound to this project ID.'))


def listing(plugin):
    """Claude manifest: the shared plugin fields plus the directory listing fields."""
    return {**plugin, 'displayName': 'Canon',
            'keywords': ['context', 'project-memory', 'sqlite', 'search', 'local-first', 'retrieval'],
            'homepage': SITE + '/canon.html', 'repository': REPOSITORY,
            'documentationUrl': REPOSITORY + '/blob/main/docs/client-packages.md',
            'supportUrl': SITE + '/plugins/canon/support.html',
            'privacyPolicyUrl': SITE + '/plugins/canon/privacy.html',
            'termsOfServiceUrl': SITE + '/plugins/canon/terms.html', 'icon': ICON,
            'userConfig': {**{key: {'type': 'string', 'title': title, 'description': text, 'required': True}
                              for key, title, text in SETTINGS},
                           'context_write': {'type': 'boolean', 'title': 'Allow context writes', 'default': False,
                               'description': 'Allow storing context in the selected database and scope. '
                                              'Turn on for the first launch to create a new database.'}}}


def manifests(version, native=False):
    plugin = {'name': 'canon-local', 'version': version,
              'description': 'Search and read project context from a local database you choose, scoped to one project.',
              'author': {'name': 'Zain Dana Harper'}, 'license': 'AGPL-3.0-only'}
    command = '${PLUGIN_ROOT}/server/canon-local.exe' if native else 'python3'
    args = [] if native else ['-I', '-S', '-B', '${PLUGIN_ROOT}/server/serve.py']
    flags = (('context-db', 'CANON_CONTEXT_DB', 'context_db'), ('workspace-id', 'CANON_WORKSPACE_ID', 'workspace_id'),
             ('project-id', 'CANON_PROJECT_ID', 'project_id'))
    portable = args + [item for flag, env, _ in flags for item in ('--' + flag, '${' + env + '}')]
    claude = [arg.replace('${PLUGIN_ROOT}', '${CLAUDE_PLUGIN_ROOT}') for arg in args]
    claude += [item for flag, _, key in flags for item in ('--' + flag, '${user_config.' + key + '}')]
    claude += ['--context-write=${user_config.context_write}']
    config = {'mcpServers': {'canon': {'command': command, 'args': portable, 'type': 'stdio'}}}
    claude_command = command.replace('${PLUGIN_ROOT}', '${CLAUDE_PLUGIN_ROOT}')
    claude_config = {'mcpServers': {'canon': {'command': claude_command, 'args': claude, 'type': 'stdio'}}}
    files = {'plugin.json': encoded(plugin), '.claude-plugin/plugin.json': encoded(listing(plugin)),
             '.codex-plugin/plugin.json': encoded({**plugin, 'skills': './skills/', 'mcpServers': './mcp.json'}),
             'mcp.json': encoded(config), '.mcp.json': encoded(claude_config)}
    if native:
        files['manifest.json'] = encoded(native_manifest(plugin))
    return files


def native_manifest(plugin):
    settings = {}
    for key, kind, title in (('context_db', 'file', 'Canon context database'),
                             ('workspace_id', 'string', 'Workspace ID'),
                             ('project_id', 'string', 'Project ID')):
        settings[key] = {'type': kind, 'title': title, 'required': True,
                         'description': 'Explicit absolute SQLite file path with an existing parent.'
                         if key == 'context_db' else 'Bind every request to this nonempty scope ID.'}
    settings['context_write'] = {'type': 'boolean', 'title': 'Allow context writes',
        'description': 'Allow storing context in the selected database and scope. Purge is unavailable.',
        'default': False, 'required': False}
    return {'manifest_version': '0.3', **plugin, 'display_name': 'Canon Local',
        'server': {'type': 'binary', 'entry_point': 'server/canon-local.exe',
                   'mcp_config': {'command': '${__dirname}/server/canon-local.exe',
                    'args': bindings('user_config.') + ['--context-write=${user_config.context_write}']}},
        'compatibility': {'platforms': ['win32']}, 'user_config': settings}
