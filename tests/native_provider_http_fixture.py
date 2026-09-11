"""Loopback HTTP fixture for native provider transport tests."""
import json
import threading
import urllib.parse
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


@contextmanager
def native_provider_server(responses):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            index = len(requests)
            body = self.rfile.read(int(self.headers["Content-Length"]))
            requests.append((self.path, dict(self.headers), body))
            response = responses[min(index, len(responses) - 1)]
            raw = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    fixture = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=fixture.serve_forever, daemon=True)
    thread.start()
    try:
        origin = f"http://127.0.0.1:{fixture.server_port}"
        yield origin, requests, MappingOpener(origin)
    finally:
        fixture.shutdown()
        fixture.server_close()
        thread.join(timeout=2)


class MappingOpener:
    """Map a validated provider Request to loopback without changing its path."""

    def __init__(self, origin):
        self.origin = origin
        self.upstream_urls = []
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def open(self, request, timeout):
        self.upstream_urls.append(request.full_url)
        parts = urllib.parse.urlsplit(request.full_url)
        mapped = self.origin + parts.path
        if parts.query:
            mapped += "?" + parts.query
        headers = {k: v for k, v in request.header_items() if k.lower() != "host"}
        loopback = urllib.request.Request(
            mapped, data=request.data, method=request.get_method(), headers=headers)
        return self._opener.open(loopback, timeout=timeout)
