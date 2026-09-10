"""Owned raw loopback fixtures; counts come from the receiving socket."""
import json
import socketserver
from contextlib import contextmanager
from threading import Event, Lock, Thread


def response(body=b'{"ok":true}', status=200, headers=b''):
    return (f'HTTP/1.1 {status} Fixture\r\nContent-Length: {len(body)}\r\n'.encode()
            + b'Connection: close\r\n' + headers + b'\r\n' + body)


@contextmanager
def server(respond=None, *, read_request=True):
    stop = Event()
    lock = Lock()
    requests = []
    connections = []

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            with lock:
                connections.append(self.client_address)
            self.request.settimeout(3)
            if not read_request:
                stop.wait(3)
                return
            try:
                data = b''
                while b'\r\n\r\n' not in data:
                    chunk = self.request.recv(4096)
                    if not chunk:
                        return
                    data += chunk
                head, body = data.split(b'\r\n\r\n', 1)
                method, path, _ = head.split(b'\r\n', 1)[0].decode().split(' ')
                headers = dict(line.split(b':', 1) for line in head.split(b'\r\n')[1:])
                length = int(next((v for k, v in headers.items() if k.lower() == b'content-length'), b'0'))
                while len(body) < length:
                    chunk = self.request.recv(min(4096, length - len(body)))
                    if not chunk:
                        return
                    body += chunk
                row = {'method': method, 'path': path, 'body': body[:length]}
                with lock:
                    requests.append(row)
                if respond:
                    respond(self.request, row, stop)
                else:
                    self.request.sendall(response())
            except (OSError, ValueError):
                pass  # Client deadline/overflow rejection closes its side.

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    receiver = Server(('127.0.0.1', 0), Handler)
    receiver.requests = requests
    receiver.connections = connections
    receiver.origin = f'http://127.0.0.1:{receiver.server_address[1]}'
    thread = Thread(target=lambda: receiver.serve_forever(poll_interval=0.01))
    thread.start()
    try:
        yield receiver
    finally:
        stop.set()
        receiver.shutdown()
        receiver.server_close()
        thread.join(3)


def gate_response(sock, row, stop):
    if row['path'] == '/health':
        obj = {'ok': True, 'model_ref': 'serve:expected'}
    elif row['path'] == '/generate':
        obj = {'text': 'active', 'model_ref': 'serve:expected', 'seed': 0}
    elif row['path'] == '/api/tags':
        obj = {'models': [{'name': 'qwen:14b', 'digest': 'sha256:abc'}]}
    else:
        obj = {'message': {'content': 'active'}, 'model': 'qwen:14b'}
    sock.sendall(response(json.dumps(obj).encode()))
