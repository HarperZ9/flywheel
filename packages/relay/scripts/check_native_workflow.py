"""Native grant qualification using fixed loopback replies, never a real model."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import threading


FIXTURE_MODEL = 'synthetic-fixture'
# An ambient gateway the launcher must clear. If it leaked through, the run would
# call this dead port instead of the fixture and fail.
AMBIENT_GATEWAY = 'http://127.0.0.1:9'


def _detail(result):
    """The server's own error code, so a failed gate names its cause."""
    try:
        body = json.loads(result['content'][0]['text'])
    except (KeyError, IndexError, TypeError, ValueError):
        return 'no structured result'
    error = body.get('error') if isinstance(body, dict) else None
    return error.get('code', 'unknown') if isinstance(error, dict) else 'no file written'


def hosted_flags(base_url):
    """The launch settings a user fills in to route online runs to one gateway."""
    return ['--api-provider=codex', f'--api-base-url={base_url}', f'--api-model={FIXTURE_MODEL}']


def check_workflow(executable, root, env, setup_args=None):
    """Run the granted workflow against fixed loopback replies.

    ``executable`` is a path or a command list. ``setup_args`` maps 'write' and
    'exec' to launch arguments, or is a callable taking the fixture base URL and
    returning that map. The launcher clears ambient hosted-model settings, so the
    fixture gateway reaches the server only through these launch arguments.
    """
    root = Path(root) / 'workflow'; root.mkdir()
    replies = []
    requests = []
    command = [str(part) for part in executable] if isinstance(executable, (list, tuple)) else [str(executable)]

    class Fixture(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(body)
            if self.path != '/chat/completions' or not replies:
                self.send_error(400); return
            payload = json.dumps({'choices': [{'message': {'content': replies.pop(0)},
                                              'finish_reason': 'stop'}]}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers(); self.wfile.write(payload)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    base_url = f'http://127.0.0.1:{server.server_port}'
    if callable(setup_args):
        setup_args = setup_args(base_url)
    write_flags = setup_args['write'] if setup_args else ['--allow-write', *hosted_flags(base_url)]
    exec_flags = setup_args['exec'] if setup_args else ['--allow-exec', *hosted_flags(base_url)]
    env = dict(env, RELAY_MCP_ROOT=str(root),
        CODEX_PROVIDER_BASE_URL=AMBIENT_GATEWAY, CODEX_MODEL='ambient-model-must-not-be-used')

    def run(flags, arguments, script):
        replies[:] = script
        request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
            'params': {'name': 'local_agent_run', 'arguments': {
                'goal': 'Native synthetic grant qualification', 'root': str(root),
                'online': True, 'backend': 'codex-provider', 'max_steps': 3, **arguments}}}
        result = subprocess.run([*command, *flags], input=json.dumps(request) + '\n',
            capture_output=True, text=True, cwd=root, env=env, timeout=45)
        if result.returncode:
            raise ValueError('native relay workflow process failed: ' + result.stderr)
        response = json.loads(result.stdout)
        if response.get('error'):
            raise ValueError('native relay workflow protocol failure')
        return response['result']

    try:
        # An explicit write grant persists the exact fixture bytes.
        result = run(write_flags, {'allow_write': True}, [
            'TOOL write_file {"path":"written.txt","content":"synthetic persistence"}', 'Fixture complete.'])
        if result.get('isError') or not (root / 'written.txt').is_file() or (root / 'written.txt').read_text() != 'synthetic persistence':
            raise ValueError('granted native write failed: ' + _detail(result))
        result = run(exec_flags, {'allow_exec': True}, [
            'TOOL run {"cmd":"echo synthetic-exec>executed.txt"}', 'Fixture complete.'])
        if result.get('isError') or not (root / 'executed.txt').is_file() or (root / 'executed.txt').read_text().strip() != 'synthetic-exec':
            raise ValueError('granted native exec failed: ' + _detail(result))
        # Per-call narrowing must win over both grants at process launch.
        before = len(requests)
        narrowed = run(exec_flags, {'allow_exec': False, 'allow_write': False}, [
            'TOOL write_file {"path":"denied-write.txt","content":"forbidden"}\n'
            'TOOL run {"cmd":"echo forbidden>denied-exec.txt"}', 'Fixture complete.'])
        if narrowed.get('isError') or len(requests) - before != 2 or replies:
            raise ValueError('native narrowing fixture did not run both turns')
        binding = json.loads(narrowed['content'][0]['text'])['request_binding']
        if binding['allow_exec'] or binding['allow_write']:
            raise ValueError('native narrowing reported broader grants')
        if (root / 'denied-write.txt').exists() or (root / 'denied-exec.txt').exists():
            raise ValueError('native per-call narrowing failed')
        before = len(requests)
        refused = run(exec_flags, {'root': str(root.parent)}, [])
        if not refused.get('isError') or len(requests) != before:
            raise ValueError('outside launch root reached the backend')
        if json.loads(refused['content'][0]['text'])['error']['code'] != 'ROOT_NOT_GRANTED':
            raise ValueError('outside root failed for a different reason')
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
    return {'status': 'PASS', 'scope': 'granted write and exec, per-call narrowing, outside-root refusal',
            'backend': 'fixed synthetic HTTP replies on loopback',
            'does_not_prove': ['model capability', 'shell filesystem confinement', 'provider compatibility']}
