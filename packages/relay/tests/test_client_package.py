"""Client artifact and actual stdio controls, using only synthetic paths."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = 'relay'
sys.path.insert(0, str(ROOT / 'scripts'))
from build_client_package import archive, build, entries, manifests, qualify


def invoke(script, tmp_path, requests, extra_env=None, args=()):
    env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP','SYSTEMDRIVE'}}
    env.update(HOME=str(tmp_path), USERPROFILE=str(tmp_path), LOCALAPPDATA=str(tmp_path), APPDATA=str(tmp_path),
               MNEME_STATE=str(tmp_path / 'synthetic.db'), RELAY_MCP_ROOT=str(tmp_path),
               RELAY_ALLOW_WRITE='1', RELAY_ALLOW_EXEC='1')
    env.update(extra_env or {})
    command = [str(script)] if script.suffix == '.exe' else [sys.executable, '-I', '-S', str(script)]
    return subprocess.run([*command,*args], input=''.join(json.dumps(r)+'\n' for r in requests),
                          capture_output=True, text=True, env=env, cwd=tmp_path, timeout=30)


def request(mid, method, **params):
    return {'jsonrpc':'2.0', 'id':mid, 'method':method, 'params':params}


@pytest.fixture
def packaged(tmp_path):
    archive_path = build(tmp_path / 'output')[0]
    target = tmp_path / 'extracted'
    with zipfile.ZipFile(archive_path) as z:
        z.extractall(target)
    return target


def test_stdio_identity_and_unknown(packaged, tmp_path):
    p = invoke(packaged / 'server/serve.py', tmp_path, [request(1,'initialize'),
        request(2,'tools/list'), request(3,'tools/call',name=TOOL+'.status',arguments={}),
        request(4,'tools/call',name='destroy_everything',arguments={})])
    assert p.returncode == 0, p.stderr
    rows = [json.loads(s) for s in p.stdout.splitlines()]
    assert rows[0]['result']['serverInfo']['version'] == qualify('dev')[0]
    assert rows[1]['result']['tools']
    assert not rows[2].get('error') and not rows[2]['result'].get('isError')
    assert rows[3].get('error') or rows[3]['result'].get('isError')
    assert not (tmp_path/'synthetic.db').exists()


def test_bad_launch_argument(packaged, tmp_path):
    p = invoke(packaged/'server/serve.py',tmp_path,[],args=['--grant-all'])
    assert p.returncode != 0 and not p.stdout


@pytest.mark.skipif(TOOL == 'plexus', reason='Plexus has no mandatory state binding')
@pytest.mark.parametrize('value',['','relative/path'])
def test_binding_required(packaged,tmp_path,value):
    key = 'MNEME_STATE' if TOOL == 'mneme' else 'RELAY_MCP_ROOT'
    p = invoke(packaged/'server/serve.py',tmp_path,[],{key:value})
    assert p.returncode != 0 and 'absolute' in p.stderr


def test_package_deterministic(tmp_path):
    first=build(tmp_path/'a')[0]; second=build(tmp_path/'b')[0]
    assert first.read_bytes() == second.read_bytes()
    with pytest.raises(FileExistsError):
        build(tmp_path/'a')


def test_linked_payload_refused(tmp_path):
    source=tmp_path/'source'; source.mkdir()
    target=tmp_path/'target'; target.mkdir()
    try:
        (source/'link').symlink_to(target,target_is_directory=True)
    except OSError:
        if os.name != 'nt':
            raise
        p=subprocess.run(['cmd','/c','mklink','/J',str(source/'link'),str(target)],capture_output=True)
        assert p.returncode == 0
    with pytest.raises(ValueError,match='linked'):
        entries(source)


def test_manifest_permissions_and_parity():
    docs=manifests(qualify('dev')[0],True)
    native=json.loads(docs['manifest.json'])
    plugin=json.loads(docs['plugin.json'])
    assert native['version'] == plugin['version']
    assert native['server']['mcp_config']['args'] == ['--write=${user_config.write}', '--exec=${user_config.exec}',
        '--api-provider=${user_config.api_provider}', '--api-base-url=${user_config.api_base_url}',
        '--api-model=${user_config.api_model}']
    assert native['server']['mcp_config']['env'] == {'RELAY_MCP_ROOT': '${user_config.local_path}',
                                                     'RELAY_API_KEY': '${user_config.api_key}'}
    assert native['user_config']['api_key']['sensitive'] is True
    assert 'annotations' not in str(docs)


def test_claude_manifest_carries_directory_listing_and_prompts_for_bindings():
    docs = manifests(qualify('dev')[0], False)
    claude = json.loads(docs['.claude-plugin/plugin.json'])
    portable = json.loads(docs['plugin.json'])
    for key in ('homepage', 'documentationUrl', 'supportUrl', 'privacyPolicyUrl', 'termsOfServiceUrl'):
        assert claude[key].startswith('https://')
    assert claude['repository'] == 'https://github.com/HarperZ9/relay'
    assert claude['displayName'] == 'Relay' and 5 <= len(claude['keywords']) <= 8
    assert all(k == k.lower() for k in claude['keywords'])
    assert claude['icon'] == './.claude-plugin/icon.png'
    config = claude['userConfig']
    assert set(config) == {'project_folder', 'write', 'exec', 'api_provider', 'api_key', 'api_base_url', 'api_model'}
    assert config['project_folder']['type'] == 'directory' and config['project_folder']['required'] is True
    assert config['write']['default'] is False and config['exec']['default'] is False
    assert config['api_key']['sensitive'] is True
    assert [k for k, v in config.items() if v.get('sensitive')] == ['api_key']
    allowed = {'type', 'title', 'description', 'required', 'default', 'sensitive'}
    assert all(set(v) <= allowed for v in config.values())
    native = json.loads(manifests(qualify('dev')[0], True)['manifest.json'])['user_config']
    for key in ('write', 'exec', 'api_provider', 'api_key', 'api_base_url', 'api_model'):
        assert config[key]['default'] == native[key]['default'] and config[key]['type'] == native[key]['type']
    for key in ('name', 'version', 'license', 'author', 'description'):
        assert claude[key] == portable[key]
    assert 'userConfig' not in portable and 'icon' not in portable
    server = json.loads(docs['.mcp.json'])['mcpServers'][TOOL]
    assert server['command'] == 'python3'
    assert server['args'][:4] == ['-I', '-S', '-B', '${CLAUDE_PLUGIN_ROOT}/server/serve.py']
    assert server['env'] == {'RELAY_MCP_ROOT': '${user_config.project_folder}',
                             'RELAY_API_KEY': '${user_config.api_key}'}
    assert not any('api_key' in a for a in server['args'])
    assert server['args'][-1] == '--no-cli-tiers'
    assert '--no-cli-tiers' not in json.loads(docs['mcp.json'])['mcpServers'][TOOL]['args']
    placeholders = [a for a in [*server['args'], *server['env'].values()] if '${' in a]
    assert all('${user_config.' in a or '${CLAUDE_PLUGIN_ROOT}' in a for a in placeholders)
    assert json.loads(docs['mcp.json'])['mcpServers'][TOOL]['env'] == {'RELAY_MCP_ROOT': '${RELAY_MCP_ROOT}'}


def test_committed_icon_is_a_square_png_the_directory_accepts():
    data = (ROOT / 'client-plugin/.claude-plugin/icon.png').read_bytes()
    assert data[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10]) and data[12:16] == b'IHDR'
    width, height = int.from_bytes(data[16:20], 'big'), int.from_bytes(data[20:24], 'big')
    assert width == height and 512 <= width <= 2048 and len(data) < 2 * 1024 * 1024


def test_committed_source_manifests_match_generated_contract():
    for name, expected in manifests(qualify('dev')[0], False).items():
        assert json.loads((ROOT / 'client-plugin' / name).read_text()) == json.loads(expected), name
    assert not (ROOT / 'client-plugin/CLAUDE.md').exists()


def test_source_zip_carries_icon_and_server_source(tmp_path):
    with zipfile.ZipFile(build(tmp_path / 'output')[0]) as z:
        names = set(z.namelist())
    assert '.claude-plugin/icon.png' in names
    assert f'server/src/{TOOL}/local_mcp.py' in names and 'server/serve.py' in names


@pytest.mark.skipif(TOOL != 'mneme', reason='Mneme scope')
def test_memory_write_refused(packaged,tmp_path):
    p=invoke(packaged/'server/serve.py',tmp_path,[request(1,'tools/call',name='mneme.remember',
             arguments={'session':'test','turns':[{'role':'user','text':'synthetic'}]})])
    assert p.returncode == 0
    assert json.loads(p.stdout)['error']
    assert not (tmp_path/'synthetic.db').exists()


@pytest.mark.skipif(TOOL != 'relay', reason='Relay scope')
def test_relay_environment_cannot_grant(packaged,tmp_path):
    p=invoke(packaged/'server/serve.py',tmp_path,[request(1,'tools/call',name='local_agent_run',
        arguments={'goal':'do not run','root':str(tmp_path),'allow_write':True,'allow_exec':True,'check':'echo forbidden'})])
    assert p.returncode == 0
    row=json.loads(p.stdout)
    assert row['result'].get('isError'),row
    assert 'GRANT' in p.stdout.upper() or 'PERMISSION' in p.stdout.upper() or 'REFUSED' in p.stdout.upper()


@pytest.mark.skipif(TOOL != 'plexus', reason='Plexus scope')
def test_declarative_discovery(packaged,tmp_path):
    p=invoke(packaged/'server/serve.py',tmp_path,[request(1,'tools/call',name='plexus_discover',arguments={})])
    assert p.returncode == 0
    result=json.loads(json.loads(p.stdout)['result']['content'][0]['text'])
    assert result['organs'] and result['edges']



def test_client_root_expansion_is_client_specific():
    docs=manifests(qualify('dev')[0],False)
    assert b'${PLUGIN_ROOT}' in docs['mcp.json']
    assert b'${CLAUDE_PLUGIN_ROOT}' in docs['.mcp.json']
    assert b'${PLUGIN_ROOT}' not in docs['.mcp.json']


def test_version_drift_refused(tmp_path,monkeypatch):
    import build_client_package as package
    (tmp_path/'pyproject.toml').write_text('[project]\nversion="0.9.0"\n')
    source=tmp_path/'src'/TOOL; source.mkdir(parents=True)
    (source/'__init__.py').write_text('__version__="0.8.0"\n')
    monkeypatch.setattr(package,'ROOT',tmp_path)
    with pytest.raises(ValueError,match='versions differ'):
        package.qualify('dev')

@pytest.mark.parametrize('name',['.env','.env.json','state.db','credential.key','secret.token'])
def test_state_and_credentials_refused_before_archiving(tmp_path,name):
    root=tmp_path/'payload'; root.mkdir()
    (root/name).write_text('synthetic-not-a-secret')
    with pytest.raises(ValueError,match='unsupported package input'):
        entries(root)


def test_unreleased_candidate_cannot_be_packaged_as_release():
    if 'unreleased' in next(line for line in (ROOT/'CHANGELOG.md').read_text().splitlines() if line.startswith('## ')).lower():
        with pytest.raises(ValueError,match='unreleased marker'):
            qualify('release')


def test_native_builder_pins_reproducibility_environment(tmp_path,monkeypatch):
    import build_client_package as package
    class StopBeforeBuild(Exception):
        pass
    def capture(command,**kwargs):
        env=kwargs['env']
        assert env['PYTHONHASHSEED']=='0'
        assert env['SOURCE_DATE_EPOCH'].isdigit()
        assert 'SYNTHETIC_SECRET' not in env
        raise StopBeforeBuild
    monkeypatch.setenv('PYTHONHASHSEED','random')
    monkeypatch.setenv('SOURCE_DATE_EPOCH','1')
    monkeypatch.setenv('SYNTHETIC_SECRET','synthetic-not-a-secret')
    monkeypatch.setattr(package.sys,'platform','win32')
    monkeypatch.setattr(package.subprocess,'run',capture)
    monkeypatch.setattr(package,'qualify',lambda mode: ('0.3.0' if TOOL=='plexus' else '0.6.0','synthetic-head'))
    monkeypatch.setattr(package.subprocess,'check_output',lambda *a,**k:'1234567890\n')
    with pytest.raises(StopBeforeBuild):
        package.build(tmp_path/'native-build',native=True)


def test_readme_and_privacy_carry_the_same_disclosure():
    def section(name):
        text = (ROOT / 'client-plugin' / name).read_text(encoding='utf-8')
        start = text.index('## What this plugin runs and handles')
        return text[start:text.index('\n## ', start + 1)].strip()
    readme = section('README.md')
    assert readme == section('PRIVACY.md')
    server = json.loads(manifests(qualify('dev')[0], False)['.mcp.json'])['mcpServers'][TOOL]
    assert ' '.join([server['command'], *server['args']]) in readme
    for name in [*server['env'], 'OPENAI_API_KEY', 'RELAY_RUN_ROOT', 'RELAY_SESSION_DIR', 'RELAY_CHILD_ENV']:
        assert f'`{name}`' in readme
