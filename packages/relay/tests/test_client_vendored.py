"""The plugin folder carries its own copy of the server code.

A directory install receives only client-plugin/, so the server must start from
that folder alone. These tests hold the committed copy to what the builder
produces, launch the exact Claude command from a copy of the folder, and check
the directory's size limits.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_client_package import ROOT, TOOL, VENDORED, build, entries, vendored_expected  # noqa: E402

PLUGIN = ROOT / 'client-plugin'
SYNC = 'python scripts/build_client_package.py --sync-vendored'


def normalized(files):
    return {name: data.replace(b'\r\n', b'\n') for name, data in files.items()}


def test_committed_vendored_copy_matches_src():
    committed = normalized(entries(PLUGIN / VENDORED))
    expected = normalized(vendored_expected())
    missing = sorted(set(expected) - set(committed))
    extra = sorted(set(committed) - set(expected))
    changed = sorted(n for n in set(expected) & set(committed) if expected[n] != committed[n])
    assert not (missing or extra or changed), (
        f'client-plugin/{VENDORED} drifted from src/{TOOL} (missing {missing}, extra {extra}, '
        f'changed {changed}). Run: {SYNC}')


def test_source_zip_takes_server_code_from_src_once(tmp_path):
    archive = build(tmp_path / 'output')[0]
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        receipt = json.loads(z.read('QUALIFICATION.json'))
    assert len(names) == len(set(names))
    assert not [n for n in receipt['source_sha256'] if n.startswith(f'client-plugin/{VENDORED}/')]
    assert sorted(n for n in names if n.startswith(VENDORED + '/')) == sorted(
        f'{VENDORED}/{n}' for n in vendored_expected())


def test_plugin_folder_fits_directory_limits():
    files = [p for p in PLUGIN.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    assert len(files) <= 512
    images = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
    assert max(p.stat().st_size for p in files if p.suffix.lower() not in images) < 256 * 1024
    assert all(p.stat().st_size < 2 * 1024 * 1024 for p in files if p.suffix.lower() in images)
    assert not [p for p in PLUGIN.rglob('.gitattributes')]


def launch(plugin, project, requests):
    server = json.loads((plugin / '.mcp.json').read_text())['mcpServers'][TOOL]
    config = json.loads((plugin / '.claude-plugin/plugin.json').read_text())['userConfig']
    values = {key: str(spec.get('default', '')).lower() if isinstance(spec.get('default'), bool)
              else spec.get('default', '') for key, spec in config.items()}
    values['project_folder'] = str(project)

    def expand(text):
        text = text.replace('${CLAUDE_PLUGIN_ROOT}', str(plugin))
        for key, value in values.items():
            text = text.replace('${user_config.' + key + '}', value)
        return text
    command = sys.executable if server['command'] == 'python3' else expand(server['command'])
    env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'SYSTEMDRIVE'}}
    env.update({k: expand(v) for k, v in server['env'].items()})
    assert '${' not in ' '.join([*map(expand, server['args']), *env.values()])
    return subprocess.run([command, *map(expand, server['args'])],
                          input=''.join(json.dumps(r) + '\n' for r in requests),
                          capture_output=True, text=True, env=env, cwd=project, timeout=60)


def isolated_copy(tmp_path):
    plugin = tmp_path / 'installed-plugin'
    shutil.copytree(PLUGIN, plugin, ignore=shutil.ignore_patterns('__pycache__'))
    project = tmp_path / 'project'
    project.mkdir()
    return plugin, project


def test_plugin_folder_alone_starts_with_the_claude_launch_command(tmp_path):
    plugin, project = isolated_copy(tmp_path)
    p = launch(plugin, project, [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}},
                                 {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}},
                                 {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                                  'params': {'name': 'relay.doctor', 'arguments': {}}}])
    assert p.returncode == 0, p.stderr
    rows = [json.loads(line) for line in p.stdout.splitlines()]
    names = {t['name'] for t in rows[1]['result']['tools']}
    assert {'local_agent_run', 'relay.status', 'relay.doctor'} <= names
    doctor = json.loads(rows[2]['result']['content'][0]['text'])
    assert doctor['cli_tiers'] == 'off in this launch profile' and 'remote' not in doctor
    assert not list(plugin.rglob('*.pyc'))


def test_missing_server_code_fails_with_one_clear_line(tmp_path):
    plugin, project = isolated_copy(tmp_path)
    shutil.rmtree(plugin / 'server' / 'src')
    p = launch(plugin, project, [{'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {}}])
    assert p.returncode == 1 and not p.stdout
    assert p.stderr.strip() == f'{TOOL}: the server code is missing from the plugin folder. Reinstall the plugin.'


SECRET_NAMES = ('RELAY_OAUTH_CLIENT_SECRET', 'RELAY_REMOTE_TOKEN', 'RELAY_OAUTH_SIGNING_SECRET',
                'RELAY_AUTHORIZE_PASSWORD')


def test_vendored_code_names_no_remote_server_secret():
    for name, data in entries(PLUGIN / VENDORED).items():
        assert not [s for s in SECRET_NAMES if s.encode() in data], name
    assert 'remote_state.py' not in vendored_expected() and 'remote_mcp.py' not in vendored_expected()


def test_closure_follows_function_imports_and_skips_marked_ones(tmp_path):
    from client_closure import SKIP_MARK, closure
    pkg = tmp_path / 'src' / 'demo'
    (pkg / 'sub').mkdir(parents=True)
    for name, text in {'__init__.py': '', 'a.py': 'def f():\n    from .b import x\n',
                       'b.py': 'x = 1\n', 'c.py': '', 'sub/__init__.py': '', 'sub/d.py': 'from .. import c\n',
                       'e.py': f'def g():\n    from . import unused  {SKIP_MARK}\n', 'unused.py': ''}.items():
        (pkg / name).write_text(text)
    entry = tmp_path / 'serve.py'
    entry.write_text('import os\nfrom demo.a import f\nfrom demo.sub import d\nfrom demo import e\n')
    assert closure(tmp_path / 'src', 'demo', entry) == {
        '__init__.py', 'a.py', 'b.py', 'c.py', 'e.py', 'sub/__init__.py', 'sub/d.py'}


def test_plugin_folder_alone_answers_every_profile_path(tmp_path):
    plugin, project = isolated_copy(tmp_path)
    calls = [('relay.status', {}), ('relay.doctor', {}), ('local_agent_health', {}),
             ('local_agent_health', {'online': True}), ('local_agent_sessions', {}),
             ('local_agent_runs', {}), ('local_agent_chat', {'prompt': 'synthetic', 'backend': 'claude-plan'})]
    p = launch(plugin, project, [{'jsonrpc': '2.0', 'id': i, 'method': 'tools/call',
                                  'params': {'name': n, 'arguments': a}} for i, (n, a) in enumerate(calls)])
    assert p.returncode == 0, p.stderr
    rows = [json.loads(line) for line in p.stdout.splitlines()]
    assert len(rows) == len(calls)
    texts = [r['result']['content'][0]['text'] for r in rows]
    assert not [t for t in texts if 'ModuleNotFoundError' in t or 'ImportError' in t]
    assert all(not r['result'].get('isError') for r in rows[:-1]), texts
    assert 'CLI_TIERS_OFF' in texts[-1]
