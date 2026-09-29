"""Live telemetry cannot extend its deadline by trickling response bytes."""
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from harness.usage_live_parse import http_text


@pytest.mark.parametrize("phase", ["headers", "body"])
def test_trickled_response_hits_total_deadline(phase):
    stop = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            head = b"HTTP/1.0 200 OK\r\nContent-Length: 100\r\n\r\n"
            payload = head if phase == "headers" else b"x" * 100
            try:
                if phase == "body":
                    self.wfile.write(head)
                    self.wfile.flush()
                for value in payload:
                    self.wfile.write(bytes([value]))
                    self.wfile.flush()
                    if stop.wait(0.04):
                        break
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        started = time.monotonic()
        with pytest.raises(RuntimeError, match="endpoint unavailable"):
            http_text(f"http://127.0.0.1:{server.server_port}/metrics", 0.25, 1024)
        assert time.monotonic() - started < 1.5
    finally:
        stop.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_http_10_body_survives_connection_close_and_redirect_is_not_followed():
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            seen.append(self.path)
            self.send_response(302 if self.path == "/redirect" else 200)
            self.send_header("Content-Length", "2")
            self.send_header("Location", "/target")
            self.end_headers()
            self.wfile.write(b"ok")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        assert http_text(base + "/metrics", 0.5, 1024) == "ok"
        with pytest.raises(RuntimeError, match="redirect refused"):
            http_text(base + "/redirect", 0.5, 1024)
        assert seen == ["/metrics", "/redirect"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
