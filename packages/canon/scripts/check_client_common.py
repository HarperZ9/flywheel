"""Synthetic process helpers shared by source and native package checks."""
import json
import os
from pathlib import Path
import subprocess
import sys


def environment(root):
    env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'SYSTEMDRIVE'}}
    env.update({key: str(root) for key in ('TEMP', 'TMP', 'HOME', 'USERPROFILE', 'LOCALAPPDATA', 'APPDATA')})
    env['PATH'] = str(Path(env.get('SYSTEMROOT', 'C:/Windows')) / 'System32')
    env['CANON_CONTEXT_MCP_PURGE'] = 'apply'
    env['CANON_CONTEXT_WRITE'] = 'true'
    return env


def binding_args(state):
    return ['--context-db', str(state), '--workspace-id', 'synthetic-workspace',
            '--project-id', 'synthetic-project']


def run(executable, root, env, args, rows=()):
    executable = Path(executable)
    command = [str(executable)] if executable.suffix == '.exe' else [sys.executable, '-I', '-S', '-B', str(executable)]
    return subprocess.run([*command, *args], input=''.join(json.dumps(row) + '\n' for row in rows),
                          capture_output=True, text=True, env=env, cwd=root, timeout=45)


def call(executable, root, env, args, name, arguments=None):
    request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
               'params': {'name': name, 'arguments': arguments or {}}}
    result = run(executable, root, env, args, [request])
    if result.returncode:
        raise ValueError('client process failed: ' + result.stderr)
    row = json.loads(result.stdout)
    if row.get('error'):
        raise ValueError('client protocol error')
    return row['result']


def value(result):
    if result.get('isError'):
        raise ValueError('client tool error: ' + str(result))
    return json.loads(result['content'][0]['text'])


def event_args():
    return {'event': {'event_id': 'synthetic-native-turn', 'source_app': 'codex',
        'message_text': 'Synthetic telescope context.', 'extractions': [
            {'source_id': 'message', 'text': 'Synthetic telescope context.',
             'claim_state': 'reported_by_source'}]}}
