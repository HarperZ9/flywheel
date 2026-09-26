"""N-28, SP-04: the pinned fetcher resolves a host once, checks every address,
connects to the checked one, ignores proxy variables, strips userinfo, and
checks every redirect hop again."""
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from harness.web_fetch_pinned import fetch_pinned


class _Recorder(BaseHTTPRequestHandler):
    seen: list = []
    redirect_to: str | None = None

    def do_GET(self):
        type(self).seen.append({"path": self.path, "host": self.headers.get("Host"),
                                "auth": self.headers.get("Authorization")})
        if type(self).redirect_to:
            self.send_response(302)
            self.send_header("Location", type(self).redirect_to)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = b"pinned page"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    _Recorder.seen, _Recorder.redirect_to = [], None
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Recorder)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def _resolver(mapping, calls):
    def resolve(host, port, **_):
        calls.append(host)
        answer = mapping[host]
        address = answer.pop(0) if isinstance(answer, list) else answer
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]
    return resolve


def _allow_loopback(address):
    return address == "127.0.0.1"


def test_a_resolver_that_changes_its_answer_cannot_redirect_the_connection(server):
    calls = []
    resolver = _resolver({"page.example": ["127.0.0.1", "10.9.9.9"]}, calls)
    status, _, body, _ = fetch_pinned(f"http://page.example:{server}/a", resolver=resolver,
                                      allow_address=_allow_loopback)
    assert (status, body) == (200, b"pinned page")
    assert calls == ["page.example"]
    assert _Recorder.seen[0]["host"] == f"page.example:{server}"


def test_proxy_variables_are_ignored(server, monkeypatch):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "ALL_PROXY"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")
    resolver = _resolver({"page.example": "127.0.0.1"}, [])
    status, *_ = fetch_pinned(f"http://page.example:{server}/b", resolver=resolver,
                              allow_address=_allow_loopback)
    assert status == 200 and _Recorder.seen[0]["path"] == "/b"


def test_userinfo_is_stripped(server):
    resolver = _resolver({"page.example": "127.0.0.1"}, [])
    fetch_pinned(f"http://user:hunter2hunter2@page.example:{server}/c", resolver=resolver,
                 allow_address=_allow_loopback)
    seen = _Recorder.seen[0]
    assert seen["auth"] is None and "user" not in seen["host"] and "hunter2" not in seen["path"]


def test_each_redirect_is_checked_again(server):
    _Recorder.redirect_to = "http://internal.example/secret"
    calls = []
    resolver = _resolver({"page.example": "127.0.0.1", "internal.example": "10.0.0.7"}, calls)
    with pytest.raises(ValueError) as blocked:
        fetch_pinned(f"http://page.example:{server}/d", resolver=resolver,
                     allow_address=_allow_loopback)
    assert "not a global address" in str(blocked.value)
    assert calls == ["page.example", "internal.example"]
    assert len(_Recorder.seen) == 1


def test_a_private_address_is_refused_before_any_connection():
    resolver = _resolver({"page.example": "192.168.1.9"}, [])
    with pytest.raises(ValueError):
        fetch_pinned("http://page.example/", resolver=resolver)


def test_web_snapshot_delegates_its_connection_to_the_pinned_fetcher(monkeypatch, tmp_path):
    from harness import web_fetch_pinned, web_snapshot
    seen = []
    monkeypatch.setattr(web_fetch_pinned, "fetch_pinned",
                        lambda url, **kw: seen.append(url) or (200, {}, b"x", url))
    doc = web_snapshot.snapshot_url("https://example.org/p", tmp_path)
    assert seen == ["https://example.org/p"] and doc["sha256"]
