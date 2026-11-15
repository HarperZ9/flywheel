import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import json
import os
import pytest
from unittest.mock import patch, MagicMock

from safe_fetch import (
    _strip_html,
    _decode,
    _cache_path,
    _summary,
    _PlainTextExtractor,
    _ALLOWED_SCHEMES,
    _DEFAULT_MAX_BYTES,
    main,
)


def test_strip_html_basic():
    html = "<html><body><p>Hello <b>world</b></p></body></html>"
    text = _strip_html(html)
    assert "Hello" in text
    assert "world" in text
    assert "<" not in text


def test_strip_html_removes_script():
    html = "<div>visible</div><script>alert('x')</script><p>also visible</p>"
    text = _strip_html(html)
    assert "visible" in text
    assert "alert" not in text


def test_strip_html_removes_style():
    html = "<style>.red{color:red}</style><p>content</p>"
    text = _strip_html(html)
    assert "content" in text
    assert "color" not in text


def test_decode_utf8():
    body = "hello".encode("utf-8")
    headers = {"Content-Type": "text/html; charset=utf-8"}
    assert _decode(body, headers) == "hello"


def test_decode_latin1():
    body = "caf\xe9".encode("latin-1")
    headers = {"Content-Type": "text/html; charset=iso-8859-1"}
    result = _decode(body, headers)
    assert "caf" in result


def test_decode_fallback():
    body = b"bytes"
    headers = {"Content-Type": "text/plain; charset=nonexistent-charset-xyz"}
    result = _decode(body, headers)
    assert result == "bytes"


def test_cache_path():
    path = _cache_path("https://example.com/page", ".safe")
    assert ".warden-safe-cache" in str(path)
    assert "fetch" in str(path)
    assert path.suffix == ".safe"


def test_summary():
    text = "line1\nline2\nline3"
    s = _summary(text, "https://example.com", "https://example.com/final")
    assert s["line_count"] == 3
    assert s["url"] == "https://example.com"
    assert s["final_url"] == "https://example.com/final"
    assert "sha256_prefix" in s


def test_allowed_schemes():
    assert "http" in _ALLOWED_SCHEMES
    assert "https" in _ALLOWED_SCHEMES
    assert "file" not in _ALLOWED_SCHEMES
    assert "ftp" not in _ALLOWED_SCHEMES


def test_plain_text_extractor_handles_nested():
    extractor = _PlainTextExtractor()
    extractor.feed("<div><p>First</p><p>Second</p></div>")
    extractor.close()
    text = extractor.text()
    assert "First" in text
    assert "Second" in text


def test_main_invalid_scheme(capsys):
    rc = main(["file:///etc/passwd", "--IO-off"])
    assert rc == 3


def test_default_max_bytes():
    assert _DEFAULT_MAX_BYTES == 2 * 1024 * 1024
