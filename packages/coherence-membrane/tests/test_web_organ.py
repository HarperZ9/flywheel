"""Tests for WebDocumentOrgan -- the membrane's web sense (Phase 1).

All offline: perception runs on fixture bytes; the one real fetch test uses a
localhost http.server, never the internet.
"""

from __future__ import annotations

import hashlib

from coherence_membrane.observation import Status
from coherence_membrane.organs.web import WebDocumentOrgan, fetch_url, perceive_html

FIXTURE = (
    b"<!doctype html><html><head><title>Hello Frontier</title>"
    b'<meta name="description" content="a test page"></head>'
    b"<body><h1>Main</h1><h2>Sub</h2>"
    b"<p>Some visible text here.</p>"
    b'<a href="https://example.com/a">A</a><a href="/b">B</a>'
    b"<script>var ignored = 1;</script>"
    b"</body></html>"
)


def test_perceive_html_extracts_structure():
    obs = perceive_html(FIXTURE, "https://test.local/")
    assert obs.organ == "web-document"
    assert obs.status == Status.PASS
    assert obs.subject == "https://test.local/"
    assert obs.data["identity_sha256"] == hashlib.sha256(FIXTURE).hexdigest()
    assert obs.data["format"] == "html"
    assert obs.data["title"] == "Hello Frontier"
    assert obs.data["meta_description"] == "a test page"
    assert obs.data["link_count"] == 2
    assert "https://example.com/a" in obs.data["links"]
    assert "Main" in obs.data["headings"]
    assert obs.data["text_len"] > 0
    assert len(obs.data["canonical_text_sha256"]) == 64


def test_script_text_is_not_perceived_as_visible_text():
    obs = perceive_html(FIXTURE, "s")
    assert "ignored" not in obs.data.get("visible_text_sample", "")


def test_provenance_digest_full_width():
    obs = perceive_html(FIXTURE, "https://test.local/")
    assert obs.provenance.digest == "sha256:" + hashlib.sha256(FIXTURE).hexdigest()
    assert obs.status in {Status.PASS, Status.WARN, Status.UNVERIFIED,
                          Status.NEEDS_HUMAN, Status.BLOCK}


def test_observe_bytes_no_network():
    obs = WebDocumentOrgan().observe(FIXTURE)[0]
    assert obs.status == Status.PASS
    assert obs.data["title"] == "Hello Frontier"


def test_nonhtml_bytes_degrade_honestly():
    payload = b"\x00\x01\x02\x03"
    obs = perceive_html(payload, "x")
    assert obs.data["identity_sha256"] == hashlib.sha256(payload).hexdigest()
    assert obs.data.get("title") in (None, "")


def test_observe_url_fetches_then_perceives(monkeypatch):
    def fake_fetch(url, *, timeout=10.0, max_bytes=5_000_000):
        return FIXTURE, {
            "http_status": 200,
            "content_type": "text/html",
            "final_url": url,
            "bytes": len(FIXTURE),
        }

    monkeypatch.setattr("coherence_membrane.organs.web.fetch_url", fake_fetch)
    obs = WebDocumentOrgan().observe("https://test.local/page")[0]
    assert obs.status == Status.PASS
    assert obs.data["http_status"] == 200
    assert obs.data["title"] == "Hello Frontier"
    assert obs.data["final_url"] == "https://test.local/page"


def test_observe_url_fetch_error_fails_closed(monkeypatch):
    def boom(url, **kwargs):
        raise OSError("no network")

    monkeypatch.setattr("coherence_membrane.organs.web.fetch_url", boom)
    obs = WebDocumentOrgan().observe("https://unreachable.local/")[0]
    assert obs.status == Status.UNVERIFIED


def test_non_http_scheme_rejected():
    obs = WebDocumentOrgan().observe("file:///etc/passwd")[0]
    assert obs.status == Status.UNVERIFIED


def test_inert_and_reproducible():
    organ = WebDocumentOrgan()
    a = organ.observe(FIXTURE)[0]
    b = organ.observe(FIXTURE)[0]
    assert a.data["identity_sha256"] == b.data["identity_sha256"]
    assert a.data["canonical_text_sha256"] == b.data["canonical_text_sha256"]


def test_fetch_url_against_localhost():
    import http.server
    import socketserver
    import threading

    html = b"<html><head><title>Local</title></head><body><p>hi</p></body></html>"

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html)

        def log_message(self, *args):
            pass

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as srv:
        port = srv.server_address[1]
        thread = threading.Thread(target=srv.handle_request, daemon=True)
        thread.start()
        payload, meta = fetch_url(f"http://127.0.0.1:{port}/")
        thread.join(timeout=5)

    assert meta["http_status"] == 200
    assert meta["content_type"].startswith("text/html")
    assert b"Local" in payload


def test_selftest_passes():
    result = WebDocumentOrgan().selftest()
    assert result.passed, result.to_dict()
    assert len(result.checks) >= 5
