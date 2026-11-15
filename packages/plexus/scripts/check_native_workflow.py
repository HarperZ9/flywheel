"""Check a synthetic declared mesh through the actual native MCP executable."""
import hashlib
import json
from pathlib import Path
import subprocess


def check_workflow(executable, root, env):
    root = Path(root) / 'workflow'; root.mkdir()
    for name, emits, consumes in [('fixture-source', ['fixture.cap/1'], []),
                                  ('fixture-target', [], ['fixture.cap/1'])]:
        (root / (name + '.interop.json')).write_text(json.dumps(
            {'organ': name, 'emits': emits, 'consumes': consumes}), encoding='utf-8')
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}

    def call(name, **arguments):
        request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                   'params': {'name': name, 'arguments': {'dir': str(root), **arguments}}}
        result = subprocess.run([str(executable)], input=json.dumps(request) + '\n',
            capture_output=True, text=True, env=env, cwd=root, timeout=45)
        if result.returncode:
            raise ValueError('native mesh workflow process failed')
        row = json.loads(result.stdout)
        if row.get('error') or row['result'].get('isError'):
            raise ValueError('native mesh workflow request failed')
        return json.loads(row['result']['content'][0]['text'])

    mesh = call('plexus_discover')
    if not any(e['producer'] == 'fixture-source' and e['consumer'] == 'fixture-target'
               and e['capability'] == 'fixture.cap/1' for e in mesh['edges']):
        raise ValueError('synthetic declared edge missing')
    path = call('plexus_route', source='fixture-source', target='fixture-target')
    if not path.get('connected') or path.get('hops') != 1:
        raise ValueError('synthetic declared route missing')
    reverse = call('plexus_route', source='fixture-target', target='fixture-source')
    if reverse.get('connected') is not False:
        raise ValueError('undeclared reverse route accepted')
    plan = call('plexus_plan', goal='fixture-target')
    if plan['order'] != ['fixture-source', 'fixture-target']:
        raise ValueError('synthetic declared order incorrect')
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
    if before != after:
        raise ValueError('declarative workflow changed fixture files')
    return {'status': 'PASS', 'scope': 'declared discovery, route, reverse-route negative, plan',
            'does_not_prove': ['runtime interoperability', 'execution of declared tools']}
