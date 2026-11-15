"""Client artifact and actual stdio controls, using only synthetic paths."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = 'plexus'
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
    assert native['server']['mcp_config']['args'] == []
    assert 'annotations' not in str(docs)


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
        arguments={'goal':'do not run','root':str(tmp_path),'allow_write':True,'allow_exec':True})])
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


def test_claude_manifest_carries_directory_listing_and_prompts_for_bindings():
    docs=manifests(qualify('dev')[0],False)
    claude=json.loads(docs['.claude-plugin/plugin.json'])
    portable=json.loads(docs['plugin.json'])
    for key in ('homepage','documentationUrl','supportUrl','privacyPolicyUrl','termsOfServiceUrl'):
        assert claude[key].startswith('https://')
    assert claude['repository'] == 'https://github.com/HarperZ9/plexus'
    assert claude['displayName'] == 'Plexus' and 5 <= len(claude['keywords']) <= 8
    assert all(k == k.lower() for k in claude['keywords'])
    assert claude['icon'] == './.claude-plugin/icon.png'
    assert {k: claude[k] for k in portable} == portable
    assert 'icon' not in portable and 'displayName' not in portable
    # Plexus takes no launch value, so there is nothing to prompt for and no placeholder to read.
    assert 'userConfig' not in claude
    server=json.loads(docs['.mcp.json'])['mcpServers'][TOOL]
    assert server['command'] == 'python3' and server['env'] == {}
    assert server['args'] == ['-I','-S','-B','${CLAUDE_PLUGIN_ROOT}/server/serve.py']
    assert json.loads(docs['.codex-plugin/plugin.json']).keys() - portable.keys() == {'skills','mcpServers'}


def test_committed_icon_is_a_square_png_the_directory_accepts():
    data=(ROOT/'client-plugin/.claude-plugin/icon.png').read_bytes()
    assert data[:8] == bytes([137,80,78,71,13,10,26,10]) and data[12:16] == b'IHDR'
    width,height=int.from_bytes(data[16:20],'big'),int.from_bytes(data[20:24],'big')
    assert width == height and 512 <= width <= 2048 and len(data) < 2*1024*1024


def test_committed_manifests_match_generated_contract():
    for name,expected in manifests(qualify('dev')[0],False).items():
        assert json.loads((ROOT/'client-plugin'/name).read_text()) == json.loads(expected), name


def test_source_zip_carries_icon_and_listing(tmp_path):
    with zipfile.ZipFile(build(tmp_path/'output')[0]) as z:
        names=set(z.namelist())
        assert z.read('.claude-plugin/icon.png') == (ROOT/'client-plugin/.claude-plugin/icon.png').read_bytes()
        assert json.loads(z.read('.claude-plugin/plugin.json'))['displayName'] == 'Plexus'
    assert 'server/src/plexus/mcp.py' in names and 'server/serve.py' in names


def test_disclosure_matches_what_the_server_imports():
    for name in ('README.md','PRIVACY.md'):
        text=(ROOT/'client-plugin'/name).read_text(encoding='utf-8')
        assert '## What this plugin runs and handles' in text
        assert 'python3 -I -S -B ${CLAUDE_PLUGIN_ROOT}/server/serve.py' in text
    # The disclosure says Plexus opens no connection, starts no program and reads no
    # environment variable. Fail if the served package gains any of those.
    import re
    for path in (ROOT/'src'/TOOL).glob('*.py'):
        code=path.read_text(encoding='utf-8')
        assert not re.search(r'^\s*(import|from)\s+(socket|subprocess|urllib|http|ssl|asyncio)(\s|\.|$)',code,re.M), path
        assert 'os.environ' not in code and 'getenv' not in code, path
    assert not (ROOT/'client-plugin/hooks').exists()


PYTHON_ENV_READS = {'COLUMNS', 'LINES', 'LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG'}
ENV_TRACER = """import io, os, runpy, sys
seen = set()
kind = type(os.environ)
for name in ('__getitem__', 'get', '__contains__'):
    def wrap(original):
        def read(self, *a, **k):
            if a and isinstance(a[0], str):
                seen.add(a[0])
            return original(self, *a, **k)
        return read
    setattr(kind, name, wrap(getattr(kind, name)))
script, requests = sys.argv[1:3]
sys.argv = [script]
sys.stdin = io.StringIO(open(requests, encoding='utf-8').read())
real, sys.stdout = sys.stdout, io.StringIO()
try:
    runpy.run_path(script, run_name='__main__')
except SystemExit:
    pass
answers, sys.stdout = sys.stdout.getvalue(), real
print(__import__('json').dumps({'reads': sorted(seen), 'answers': answers.count(chr(10))}))
"""


def test_traced_environment_reads_are_the_disclosed_python_reads(packaged, tmp_path):
    calls = [('plexus_discover', {}), ('plexus_wiring', {}), ('plexus_plan', {'goal': 'crucible'}),
             ('plexus_route', {'source': 'gather', 'target': 'crucible'}),
             ('plexus.status', {}), ('plexus.doctor', {})]
    rows = [request(1, 'initialize'), request(2, 'tools/list')]
    rows += [request(3 + i, 'tools/call', name=n, arguments=a) for i, (n, a) in enumerate(calls)]
    (tmp_path / 'requests.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
    (tmp_path / 'tracer.py').write_text(ENV_TRACER, encoding='utf-8')
    p = subprocess.run([sys.executable, '-I', '-S', '-B', str(tmp_path / 'tracer.py'),
                        str(packaged / 'server/serve.py'), str(tmp_path / 'requests.jsonl')],
                       capture_output=True, text=True, cwd=tmp_path, timeout=60)
    assert p.returncode == 0, p.stderr
    trace = json.loads(p.stdout.splitlines()[-1])
    assert trace['answers'] == len(rows)
    # The tracer must see reads at all, or an empty set would pass vacuously.
    assert trace['reads'] and set(trace['reads']) <= PYTHON_ENV_READS, trace['reads']
    for name in ('README.md', 'PRIVACY.md'):
        text = (ROOT / 'client-plugin' / name).read_text(encoding='utf-8')
        assert all(f'`{key}`' in text for key in PYTHON_ENV_READS), name
        assert "Plexus's own code reads no environment variable" in text


def lf(data):
    return data.replace(b'\r\n', b'\n')


def test_vendored_server_code_matches_the_builder():
    import build_client_package as package
    target = ROOT / 'client-plugin' / package.VENDORED
    committed = {path.relative_to(target).as_posix(): lf(path.read_bytes())
                 for path in target.rglob('*') if path.is_file()
                 and '__pycache__' not in path.parts and path.suffix != '.pyc'}
    expected = {name: lf(data) for name, data in package.vendored().items()}
    hint = f'client-plugin/server/src is stale; run: {package.SYNC_COMMAND}'
    assert sorted(committed) == sorted(expected), hint
    assert [n for n in expected if committed[n] != expected[n]] == [], hint


def test_builder_counts_the_vendored_copy_once(tmp_path):
    import build_client_package as package
    assert not any(name.startswith(package.VENDORED) for name in package.client_entries())
    with zipfile.ZipFile(build(tmp_path / 'output')[0]) as z:
        names = z.namelist()
        receipt = json.loads(z.read('QUALIFICATION.json'))
    assert len(names) == len(set(names))
    assert sorted(n for n in names if n.startswith(package.VENDORED)) == \
        sorted(package.VENDORED + n for n in package.vendored())
    assert not any(n.startswith('client-plugin/server/src/') for n in receipt['source_sha256'])


def isolated_launch(plugin, tmp_path, requests):
    server = json.loads((plugin / '.mcp.json').read_text(encoding='utf-8'))['mcpServers'][TOOL]
    def resolve(value):
        assert '${user_config.' not in value  # Plexus declares no userConfig
        return value.replace('${CLAUDE_PLUGIN_ROOT}', str(plugin))
    command = sys.executable if server['command'] == 'python3' else resolve(server['command'])
    env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'PATH'}}
    env.update({k: resolve(v) for k, v in server.get('env', {}).items()})
    return subprocess.run([command, *map(resolve, server['args'])], env=env, cwd=tmp_path, timeout=60,
                          input=''.join(json.dumps(r) + '\n' for r in requests), capture_output=True, text=True)


def test_plugin_folder_alone_launches_with_the_claude_command(tmp_path):
    plugin = tmp_path / 'installed'
    shutil.copytree(ROOT / 'client-plugin', plugin, ignore=shutil.ignore_patterns('__pycache__'))
    p = isolated_launch(plugin, tmp_path, [request(1, 'initialize'), request(2, 'tools/list')])
    assert p.returncode == 0, p.stderr
    rows = [json.loads(line) for line in p.stdout.splitlines()]
    assert rows[0]['result']['serverInfo']['name'] == TOOL
    assert {t['name'] for t in rows[1]['result']['tools']} == {
        'plexus_discover', 'plexus_wiring', 'plexus_plan', 'plexus_route', 'plexus.status', 'plexus.doctor'}
    shutil.rmtree(plugin / 'server' / 'src')
    p = isolated_launch(plugin, tmp_path, [request(1, 'tools/list')])
    assert p.returncode == 1 and not p.stdout
    assert p.stderr.strip() == 'plexus: the server code is missing from the plugin folder. Reinstall the plugin.'


def test_plugin_folder_fits_the_directory_limits():
    files = [path for path in (ROOT / 'client-plugin').rglob('*')
             if path.is_file() and '__pycache__' not in path.parts]
    assert len(files) <= 512
    # The 256 KiB rule covers code and text. Images and fonts are exempt; the icon stays under 2 MB.
    exempt = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.woff', '.woff2', '.ttf', '.otf'}
    assert [p.name for p in files if p.suffix.lower() not in exempt and p.stat().st_size >= 256 * 1024] == []
    assert [p.name for p in files if p.stat().st_size >= 2 * 1024 * 1024] == []
    assert not [p for p in files if p.name == '.gitattributes']


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
