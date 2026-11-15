"""Check a built native Node client archive without touching operator state."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import zipfile

from build_client_plugin import ROOT, NODE_HASHES


def validate_assessment(result):
    content = json.loads(result['content'][0]['text'])
    if content.get('status') != 'halted-assess' or content.get('haltedAt') != 0:
        raise ValueError('graded assessment did not halt at the first step')
    if not content.get('steps'):
        raise ValueError('assessment halt has no witnessed steps')


def check(archive):
    config = json.loads((ROOT / 'client-plugin/config.json').read_text())
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(archive) as z:
            names = z.namelist()
            if len(set(names)) != len(names):
                raise ValueError('duplicate archive members')
            source = json.loads(z.read('SOURCE.json'))
            if set(names) != set(source['payload_sha256']) | {'SOURCE.json'}:
                raise ValueError('archive and source receipt disagree')
            for name in names:
                parts = PurePosixPath(name).parts
                if name != '/'.join(parts) or '\\' in name or ':' in name or any(p in {'.', '..'} for p in parts) or name.startswith('/'):
                    raise ValueError('unsafe archive path')
                content = z.read(name)
                if name != 'SOURCE.json' and hashlib.sha256(content).hexdigest() != source['payload_sha256'][name]:
                    raise ValueError('payload hash mismatch')
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
        for name, digest in NODE_HASHES.items():
            if hashlib.sha256((root / 'runtime' / name).read_bytes()).hexdigest() != digest:
                raise ValueError('runtime pin mismatch')
        env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','COMSPEC','PATHEXT'}}
        env.update(HOME=str(root/'home'),USERPROFILE=str(root/'home'),LEARN_HOME=str(root/'state'))
        env['PATH'] = os.path.join(os.environ.get('SYSTEMROOT','C:/Windows'), 'System32')
        requests = [{'jsonrpc':'2.0','id':1,'method':'initialize','params':{}},
                    {'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}},
                    {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{
                        'name':'learn_dry_run' if config['tool']=='learn' else 'telos.catalog',
                        'arguments':{'workflow':{'steps':[{'kind':'assess'}]}} if config['tool']=='learn' else {}}}]
        command = [str(root/'runtime/node.exe'),str(root/config['entry'])]
        result = subprocess.run(command, input=''.join(json.dumps(x)+'\n' for x in requests),
                                env=env,cwd=root,text=True,capture_output=True,timeout=30)
        if result.returncode:
            raise ValueError('native MCP process failed')
        messages = {v['id']:v for v in map(json.loads,result.stdout.splitlines()) if 'id' in v}
        if messages[1]['result']['serverInfo']['version'] != source['version']:
            raise ValueError('server version mismatch')
        if messages[3].get('error') or messages[3]['result'].get('isError'):
            raise ValueError('safe synthetic workflow failed')
        if config['tool']=='learn':
            validate_assessment(messages[3]['result'])
        return {'status':'PASS','archive_sha256':hashlib.sha256(Path(archive).read_bytes()).hexdigest(),
                'version':source['version'],'tools':len(messages[2]['result']['tools']),
                'checks':['source hashes','pinned bundled runtime','stdio initialize/list','safe synthetic workflow'],
                'does_not_prove':['installed client compatibility','marketplace approval','global network isolation']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    args=parser.parse_args()
    print(json.dumps(check(args.archive),indent=2))
