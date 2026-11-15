"""Package contracts and release gates using synthetic source trees."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_client_package as package
import client_package_inputs as source

checkout_only = pytest.mark.skipif(
    (ROOT / 'PKG-INFO').is_file() and not (ROOT / '.git').exists(),
    reason='an extracted sdist has no Git identity for client release construction',
)


def test_manifests_bind_arguments_and_default_to_read_only():
    docs = package.manifests('0.5.0', True)
    manifest = json.loads(docs['manifest.json'])
    config = manifest['server']['mcp_config']
    assert config['args'] == ['--context-db', '${user_config.context_db}',
        '--workspace-id', '${user_config.workspace_id}', '--project-id', '${user_config.project_id}',
        '--context-write=${user_config.context_write}']
    assert manifest['user_config']['context_write']['default'] is False
    assert all(manifest['user_config'][key]['required'] for key in ('context_db', 'workspace_id', 'project_id'))
    assert 'purge' not in config and 'env' not in config
    assert b'${CLAUDE_PLUGIN_ROOT}' in docs['.mcp.json']
    assert b'${PLUGIN_ROOT}' not in docs['.mcp.json']
    assert b'${PLUGIN_ROOT}' in docs['mcp.json']


def test_claude_manifest_carries_directory_listing_and_prompts_for_bindings():
    docs = package.manifests('0.5.0')
    claude = json.loads(docs['.claude-plugin/plugin.json'])
    portable = json.loads(docs['plugin.json'])
    for key in ('homepage', 'documentationUrl', 'supportUrl', 'privacyPolicyUrl', 'termsOfServiceUrl'):
        assert claude[key].startswith('https://')
    assert claude['repository'] == 'https://github.com/HarperZ9/canon'
    assert claude['displayName'] == 'Canon' and 5 <= len(claude['keywords']) <= 8
    assert set(claude['userConfig']) == {'context_db', 'workspace_id', 'project_id', 'context_write'}
    assert claude['userConfig']['context_write']['default'] is False
    assert not set(claude) - set(portable) & {'name', 'version', 'license', 'author', 'description'}
    assert 'userConfig' not in portable and 'icon' not in portable
    args = json.loads(docs['.mcp.json'])['mcpServers']['canon']['args']
    assert [a for a in args if '${' in a] == ['${CLAUDE_PLUGIN_ROOT}/server/serve.py',
        '${user_config.context_db}', '${user_config.workspace_id}', '${user_config.project_id}',
        '--context-write=${user_config.context_write}']
    assert '${CANON_CONTEXT_DB}' in json.loads(docs['mcp.json'])['mcpServers']['canon']['args']


@checkout_only
def test_committed_icon_is_a_square_png_the_directory_accepts():
    data = (ROOT / 'client-plugin/.claude-plugin/icon.png').read_bytes()
    assert data[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10]) and data[12:16] == b'IHDR'
    width, height = int.from_bytes(data[16:20], 'big'), int.from_bytes(data[20:24], 'big')
    assert width == height and 512 <= width <= 2048 and len(data) < 2 * 1024 * 1024


@checkout_only
def test_committed_source_manifests_match_generated_contract():
    version = package.qualify('dev')[0]
    for name, expected in package.manifests(version).items():
        assert json.loads((ROOT / 'client-plugin' / name).read_text()) == json.loads(expected)
    root_plugin = json.loads((ROOT / '.claude-plugin/plugin.json').read_text())
    plugin = json.loads(package.manifests(version)['.claude-plugin/plugin.json'])
    assert root_plugin == {**plugin, 'icon': './client-plugin/.claude-plugin/icon.png',
                           'skills': './client-plugin/skills/'}
    root_mcp = json.loads((ROOT / '.mcp.json').read_text())
    expected_mcp = package.manifests(version)['.mcp.json'].replace(
        b'/server/serve.py', b'/client-plugin/server/serve.py')
    assert root_mcp == json.loads(expected_mcp)


@checkout_only
def test_source_archive_is_deterministic_and_hashes_every_payload(tmp_path):
    first = package.build(tmp_path / 'one')[0]
    second = package.build(tmp_path / 'two')[0]
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert 'server/src/canon/_version.py' in archive.namelist()
        assert 'server/serve.py' in archive.namelist()
        rows = archive.read('PAYLOAD-SHA256SUMS').decode().splitlines()
        checked = set()
        for row in rows:
            digest, name = row.split('  ', 1)
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
            checked.add(name)
        assert checked == set(archive.namelist()) - {'PAYLOAD-SHA256SUMS'}
    with pytest.raises(FileExistsError):
        package.build(tmp_path / 'one')


@pytest.mark.parametrize('name', ['.env', '.env.json', 'state.db', 'credentials.key'])
def test_package_refuses_state_and_credentials(tmp_path, name):
    (tmp_path / name).write_text('synthetic')
    with pytest.raises(ValueError, match='unsupported package input'):
        source.entries(tmp_path)


@pytest.fixture
def release_tree(tmp_path):
    (tmp_path / 'src/canon').mkdir(parents=True)
    (tmp_path / 'src/canon/_version.py').write_text('__version__ = "0.5.0"\n')
    (tmp_path / 'pyproject.toml').write_text('[project]\nversion = "0.5.0"\n')
    (tmp_path / 'CHANGELOG.md').write_text('## 0.5.0 - 2026-10-01\n')
    for args in (['init'], ['config', 'user.email', 'synthetic@example.invalid'],
                 ['config', 'user.name', 'Synthetic'], ['add', '.'],
                 ['commit', '-m', 'synthetic release'], ['tag', 'v0.5.0']):
        subprocess.run(['git', *args], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def test_release_requires_clean_exact_tag(release_tree):
    assert source.qualify(release_tree, 'release')[0] == '0.5.0'
    (release_tree / 'extra.txt').write_text('unexpected')
    with pytest.raises(ValueError, match='clean'):
        source.qualify(release_tree, 'release')
    subprocess.run(['git', 'add', '.'], cwd=release_tree, check=True, capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'later'], cwd=release_tree, check=True, capture_output=True)
    with pytest.raises(ValueError, match='tag must identify'):
        source.qualify(release_tree, 'release')


@pytest.mark.parametrize('version, heading, message', [
    ('0.5.1', '## 0.5.1 - 2026-10-01', 'end in .0'),
    ('0.5.0', '## 0.5.0 - Unreleased', 'unreleased marker')])
def test_release_rejects_nonfinal_versions(release_tree, version, heading, message):
    (release_tree / 'src/canon/_version.py').write_text(f'__version__ = "{version}"\n')
    (release_tree / 'pyproject.toml').write_text(f'[project]\nversion = "{version}"\n')
    (release_tree / 'CHANGELOG.md').write_text(heading + '\n')
    with pytest.raises(ValueError, match=message):
        source.qualify(release_tree, 'release')


def test_version_drift_is_refused(release_tree):
    (release_tree / 'src/canon/_version.py').write_text('__version__ = "0.4.2"\n')
    with pytest.raises(ValueError, match='versions differ'):
        source.qualify(release_tree, 'dev')


def test_ignored_untracked_authored_inputs_cannot_enter_release(release_tree):
    (release_tree / 'client-plugin').mkdir()
    (release_tree / 'scripts').mkdir()
    (release_tree / 'LICENSE').write_text('synthetic')
    (release_tree / '.gitignore').write_text('scripts/\n')
    subprocess.run(['git', 'add', '.'], cwd=release_tree, check=True, capture_output=True)
    (release_tree / 'scripts/ambient.py').write_text('print("unexpected")')
    with pytest.raises(ValueError, match='tracked authored'):
        source.inputs(release_tree, 'release')


def test_changed_or_new_inputs_refused(release_tree):
    (release_tree / 'client-plugin').mkdir()
    (release_tree / 'scripts').mkdir()
    (release_tree / 'LICENSE').write_text('synthetic')
    before = source.inputs(release_tree, 'dev')
    head = source.git(release_tree, 'rev-parse', 'HEAD')
    (release_tree / 'scripts/new.py').write_text('new input')
    with pytest.raises(ValueError, match='source changed'):
        source.unchanged(release_tree, before, 'dev', head)


def test_native_environment_uses_explicit_long_temp_and_isolated_home(tmp_path, monkeypatch):
    import native_client_build as native
    monkeypatch.setenv('SYNTHETIC_SECRET', 'synthetic')
    monkeypatch.setenv('TEMP', 'C:/SHORT~1/TEMP')
    monkeypatch.setenv('CANON_CONTEXT_MCP_PURGE', 'apply')
    monkeypatch.setattr(native, 'git', lambda *args: '1234567890')
    env = native.build_environment(tmp_path, ROOT, 'test')
    assert env['TEMP'] == env['TMP'] == str((tmp_path / 'temp').resolve())
    assert env['HOME'] == env['USERPROFILE'] == str((tmp_path / 'home').resolve())
    assert env['SOURCE_DATE_EPOCH'] == '1234567890' and env['PYTHONHASHSEED'] == '0'
    assert 'SYNTHETIC_SECRET' not in env and 'CANON_CONTEXT_MCP_PURGE' not in env


def test_native_dependency_outside_runtime_is_refused(tmp_path):
    from native_build_provenance import dependencies
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    outside = tmp_path / 'ambient.dll'
    outside.write_bytes(b'synthetic')
    toc = tmp_path / 'Analysis-00.toc'
    toc.write_text(repr([('ambient.dll', str(outside), 'BINARY')]))
    with pytest.raises(ValueError, match='outside Python runtime'):
        dependencies(toc, runtime)


@pytest.mark.parametrize('flag', ['--assume-unchanged', '--skip-worktree'])
def test_hidden_modified_release_input_is_refused(release_tree, flag):
    name = 'src/canon/_version.py'
    subprocess.run(['git', 'update-index', flag, name], cwd=release_tree, check=True, capture_output=True)
    (release_tree / name).write_text('__version__ = "0.5.0"\n# changed hidden source\n')
    assert not source.git(release_tree, 'status', '--porcelain')
    with pytest.raises(ValueError, match='assume-unchanged or skip-worktree'):
        source.verify_head_inputs(release_tree, {name: (release_tree / name).read_bytes()})


def test_head_comparison_checks_bytes_even_without_hidden_flags(release_tree):
    name = 'src/canon/_version.py'
    source.verify_head_inputs(release_tree, {name: (release_tree / name).read_bytes()})
    (release_tree / name).write_text('__version__ = "0.5.0"\n# edited\n')
    with pytest.raises(ValueError, match='bytes differ from HEAD'):
        source.verify_head_inputs(release_tree, {name: (release_tree / name).read_bytes()})


@checkout_only
def test_vendored_server_source_matches_src():
    committed, expected = package.committed_vendored(), package.vendored_files()
    drift = sorted(set(committed) ^ set(expected)) + sorted(
        name for name in set(committed) & set(expected) if committed[name] != expected[name])
    assert not drift, ('client-plugin/server/src differs from src/canon; run '
                       '`python scripts/build_client_package.py --sync-vendored`: ' + ', '.join(drift[:10]))


def _launch(folder, values):
    """The Claude launch from .mcp.json with the plugin root and user settings filled in."""
    entry = json.loads((folder / '.mcp.json').read_text())['mcpServers']['canon']
    def fill(arg):
        arg = arg.replace('${CLAUDE_PLUGIN_ROOT}', folder.as_posix())
        for key, value in values.items():
            arg = arg.replace('${user_config.' + key + '}', value)
        return arg
    assert entry['command'] == 'python3'
    return [sys.executable] + [fill(arg) for arg in entry['args']]


def _rpc(command, cwd):
    requests = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                    'protocolVersion': '2025-06-18', 'capabilities': {},
                    'clientInfo': {'name': 'isolated-launch-test', 'version': '1'}}},
                {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}]
    return subprocess.run(command, input=''.join(json.dumps(r) + '\n' for r in requests),
                          capture_output=True, text=True, timeout=120, cwd=cwd)


@checkout_only
def test_plugin_folder_alone_starts_and_lists_tools(tmp_path):
    import shutil
    folder = tmp_path / 'installed' / 'canon-local'
    shutil.copytree(ROOT / 'client-plugin', folder, ignore=shutil.ignore_patterns('__pycache__'))
    values = {'context_db': (tmp_path / 'context.db').as_posix(), 'workspace_id': 'w',
              'project_id': 'p', 'context_write': 'true'}
    done = _rpc(_launch(folder, values), tmp_path)
    replies = [json.loads(line) for line in done.stdout.splitlines() if line.strip()]
    tools = [tool['name'] for reply in replies if reply.get('id') == 2 for tool in reply['result']['tools']]
    assert {'canon.context.health', 'canon.context.query', 'canon.context.get'} <= set(tools), done.stderr
    shutil.rmtree(folder / 'server' / 'src')
    missing = _rpc(_launch(folder, values), tmp_path)
    assert missing.returncode == 1
    assert 'server code is missing from the plugin folder' in missing.stderr


@checkout_only
def test_plugin_folder_stays_inside_directory_file_limits():
    files = [path for path in (ROOT / 'client-plugin').rglob('*')
             if path.is_file() and '__pycache__' not in path.parts]
    assert len(files) <= 512
    images = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
    assert [p.name for p in files if p.suffix not in images and p.stat().st_size >= 256 * 1024] == []
