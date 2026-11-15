"""Run synthetic protocol, persistence and setup gates on actual packaged bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from check_client_common import binding_args, call, environment, run, value
from check_mcpb_setup import check_setup
from check_native_workflow import check_workflow
from client_manifests import manifests


def check(executable, version):
    with tempfile.TemporaryDirectory(prefix='canon-client-') as temp:
        root = Path(temp)
        env = environment(root)
        args = binding_args(root / 'context.sqlite')
        value(call(executable, root, env, [*args, '--context-write=true'], 'canon.context.health'))
        rows = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'},
                {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}]
        result = run(executable, root, env, args, rows)
        if result.returncode:
            raise ValueError('packaged protocol process failed: ' + result.stderr)
        answers = [json.loads(line) for line in result.stdout.splitlines()]
        if len(answers) != 2 or answers[0]['result']['serverInfo']['version'] != version:
            raise ValueError('packaged protocol/version mismatch')
        names = {tool['name'] for tool in answers[1]['result']['tools']}
        if names != {'canon.context.health', 'canon.context.query', 'canon.context.get'}:
            raise ValueError('default tool list differs from read-only contract')
        for bad_args in ([], [*args, '--grant-all'], [*args, '--context-write=yes']):
            refused = run(executable, root, env, bad_args)
            if not refused.returncode or refused.stdout:
                raise ValueError('missing binding or unknown grant accepted')
        manifest = json.loads(manifests(version, True)['manifest.json'])
        setup = check_setup(executable, manifest, env, root, root / 'context.sqlite')
        workflow = check_workflow(executable, root)
    return {'status': 'PASS', 'version': version, 'mcpb_setup': setup, 'workflow': workflow,
        'executable_sha256': hashlib.sha256(Path(executable).read_bytes()).hexdigest(),
        'does_not_prove': ['model workflow', 'installed client compatibility', 'clean OS compatibility']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.executable, args.version), indent=2))
