"""Exercise an actual frozen local binary without Python on its PATH."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_windows_process import run_process

SOURCE = 'The sample contains 14 records.'
TOOLS = {'check', 'score', 'judge', 'fix', 'polish', 'edit_plan', 'edit_submit',
         'articulate.status', 'articulate.doctor', 'corpus_check', 'title_workshop',
         'interview', 'restructure_plan', 'voice_compare', 'voice_apply_plan',
         'house_brief', 'house_transform', 'dialogue_check'}
HOUSE_IN = 'Great question! The sample has 14 records—all checked.'
HOUSE_OUT = 'The sample has 14 records, all checked.'


def require(value, message):
    if not value:
        raise ValueError(message)


def call(rid, name, arguments):
    return {'jsonrpc': '2.0', 'id': rid, 'method': 'tools/call',
            'params': {'name': name, 'arguments': arguments}}


def start():
    return [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
        'protocolVersion': '2025-06-18', 'capabilities': {'sampling': {}},
        'clientInfo': {'name': 'native-qualification', 'version': '1'}}},
        {'jsonrpc': '2.0', 'method': 'notifications/initialized'}]


def parse(stdout, ids):
    rows = {}
    for line in stdout.splitlines():
        row = strict_json(line)
        require(set(row) == {'jsonrpc', 'id', 'result'}, 'unsolicited request or invalid response')
        require(type(row['id']) is int and row['id'] in ids and row['id'] not in rows,
                'unexpected or duplicate response ID')
        require(row['jsonrpc'] == '2.0', 'wrong protocol')
        rows[row['id']] = row['result']
    require(set(rows) == ids, 'missing response')
    return rows


def strict_json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique,
                      parse_constant=lambda _: require(False, 'nonfinite JSON value'))


def payload(result, error=False):
    require(result.get('isError', False) is error, 'wrong tool error status')
    require(len(result['content']) == 1 and result['content'][0]['type'] == 'text', 'invalid content')
    value = strict_json(result['content'][0]['text'])
    require(isinstance(value, dict), 'invalid tool payload')
    require('structuredContent' not in result or result['structuredContent'] == value,
            'conflicting tool payload')
    return value


def run(exe, requests, env, home):
    code, stdout, stderr = run_process(exe, [], env, home, ''.join(json.dumps(r) + '\n' for r in requests))
    require(code == 0 and not stderr, 'server failed or emitted stderr')
    return parse(stdout, {r['id'] for r in requests if 'id' in r})


def validate_initialize(result, version):
    require(result.get('protocolVersion') == '2025-06-18' and
            result.get('serverInfo') == {'name': 'articulate', 'version': version},
            'wrong protocol or binary version')


def validate_refusal(result, tool, backend):
    value = payload(result, error=True)
    require(value.get('ok') is False and value.get('error') ==
            f"{tool} backend '{backend}' is not available in local-only mode", 'backend accepted')


def validate_submission(result, expected, refused):
    value = payload(result)
    require(value.get('ok') is True and value.get('backend') == 'host' and
            value.get('text') == expected and isinstance(value.get('refused'), list) and
            bool(value['refused']) is refused, 'host submission or guard failed')
    receipt = value.get('receipt', {})
    require(receipt.get('backend') == 'host' and receipt.get('attempts') == [], 'model used for edit')
    require(receipt.get('original_sha256') == 'sha256:' + hashlib.sha256(SOURCE.encode()).hexdigest()
            and receipt.get('text_sha256') == 'sha256:' + hashlib.sha256(expected.encode()).hexdigest(),
            'invalid submission receipt hashes')


def check(executable, version):
    exe = Path(executable).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='articulate-native-') as temporary, socket.socket() as closed:
        home = Path(temporary)
        closed.bind(('127.0.0.1', 0))
        endpoint = f'http://127.0.0.1:{closed.getsockname()[1]}'
        windows = os.environ.get('SYSTEMROOT', 'C:/Windows')
        env = {'SYSTEMROOT': windows, 'WINDIR': windows, 'PATH': str(Path(windows) / 'System32'),
               'ARTICULATE_LOCAL_ONLY': '0', 'ARTICULATE_MCP_TOOLS': 'all',
               'ARTICULATE_BACKEND': 'openai', 'ARTICULATE_OPENAI_BASE_URL': endpoint,
               'ARTICULATE_OLLAMA_URL': endpoint, 'OPENAI_BASE_URL': endpoint,
               'ANTHROPIC_BASE_URL': endpoint, 'HTTP_PROXY': endpoint, 'HTTPS_PROXY': endpoint}
        env.update({k: temporary for k in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP')})
        requests = start() + [{'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
                             call(3, 'articulate.doctor', {}), call(4, 'check', {'text': SOURCE}),
                             call(5, 'edit_plan', {'text': SOURCE})]
        for tool in ('fix', 'judge', 'polish'):
            for backend in ('anthropic', 'openai', 'claude-cli', 'sampling', 'ollama'):
                requests.append(call(len(requests), tool, {'text': SOURCE, 'backend': backend}))
        rows = run(exe, requests, env, home)
        validate_initialize(rows[1], version)
        require({t['name'] for t in rows[2]['tools']} == TOOLS and len(rows[2]['tools']) == len(TOOLS), 'wrong tools')
        require(all(t['annotations']['openWorldHint'] is False for t in rows[2]['tools']), 'open-world tool')
        doctor = payload(rows[3])
        require(doctor['tool_set'] == 'local' and doctor['local_only_switch'] is True, 'widened environment')
        require('verdict' in payload(rows[4]), 'core check missing')
        plan = payload(rows[5])
        require(plan['status'] == 'host_edit_required' and plan['attempts'] == [], 'model used for plan')
        for request in requests:
            if request.get('id', 0) >= 6:
                params = request['params']
                validate_refusal(rows[request['id']], params['name'], params['arguments']['backend'])
        second = run(exe, start() + [call(2, 'edit_submit', {'text': SOURCE,
            'rewrite': plan['masked_text'].replace('contains', 'has'), 'plan_id': plan['plan_id']}),
            call(3, 'edit_submit', {'text': SOURCE, 'rewrite': SOURCE.replace('14', '15'),
                                  'plan_id': plan['plan_id']}),
            # Reads the packaged house voice spec, which the frozen binary must carry.
            call(4, 'house_transform', {'text': HOUSE_IN})], env, home)
        validate_initialize(second[1], version)
        validate_submission(second[2], SOURCE.replace('contains', 'has'), False)
        validate_submission(second[3], SOURCE, True)
        require(payload(second[4]).get('text') == HOUSE_OUT, 'house voice spec missing or edit wrong')
        code, stdout, stderr = run_process(exe, ['--backend=openai'], env, home, '')
        require(code == 2 and not stdout and stderr == 'articulate-local accepts no arguments\n',
                'launch arguments accepted')
    return {'status': 'PASS', 'version': version, 'executable_sha256': hashlib.sha256(exe.read_bytes()).hexdigest(),
            'local_tools': sorted(TOOLS), 'host_edit_roundtrip': True, 'changed_fact_refused': True,
            'house_spec_bundled': True,
            'backend_refusals': 15, 'python_on_path': False, 'hostile_environment_overridden': True,
            'scope': ('Checks the executable hash, the local tool list, a host edit round '
                      'trip, the refusal of a changed fact and the backend refusals.')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable')
    parser.add_argument('--version', required=True)
    parser.add_argument('--receipt', required=True)
    args = parser.parse_args()
    result = check(args.executable, args.version)
    Path(args.receipt).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
