from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from secret_redact_io import fetch_guarded


class SecretHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = ("api_key=sk-" + ("a" * 48)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


def test_fetch_guarded_redacts_body_from_local_http_server() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), SecretHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/secret"
        result = fetch_guarded(url, timeout=2)
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert result.status_code == 200
    assert "sk-" not in result.text
    assert "[REDACTED:openai_api_key]" in result.text
    assert result.receipt.operation == "fetch"
    assert result.receipt.metadata["status_code"] == 200
