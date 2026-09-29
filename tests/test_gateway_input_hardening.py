"""Static files and temperature input fail closed before side effects."""
from io import BytesIO
from pathlib import Path

import pytest

from harness import gateway
from harness.proposer import ProposerOutput


def _static(root, path):
    handler = object.__new__(gateway._Handler)
    handler.root = root
    handler.wfile = BytesIO()
    handler.command = "GET"
    statuses, headers = [], {}
    handler.send_response = statuses.append
    handler.send_header = headers.__setitem__
    handler.end_headers = lambda: None
    handler._static(path)
    assert len(statuses) == 1
    return statuses[0], headers, handler.wfile.getvalue()


@pytest.mark.parametrize("relative", [
    ".env", ".git/config", "site/.cache/config.json", "site/.private.html",
    ".secrets/public.html",
])
def test_static_refuses_hidden_segments(tmp_path, relative):
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"private-static-marker")
    status, _, body = _static(tmp_path, "/" + relative)
    assert status in {403, 404}
    assert b"private-static-marker" not in body


@pytest.mark.parametrize("relative", ["key.pem", "notes.txt", "server.py", "no_extension"])
def test_static_refuses_unknown_extensions(tmp_path, relative):
    (tmp_path / relative).write_bytes(b"private-static-marker")
    status, _, body = _static(tmp_path, "/" + relative)
    assert status in {403, 404}
    assert b"private-static-marker" not in body


@pytest.mark.parametrize("path_style", ["traversal", "absolute"])
def test_static_refuses_outside_root(tmp_path, path_style):
    root = tmp_path / "site-root"
    root.mkdir()
    outside = tmp_path / "outside.html"
    outside.write_bytes(b"outside-static-marker")
    path = "/../outside.html" if path_style == "traversal" else str(outside)
    status, _, body = _static(root, path)
    assert status in {403, 404}
    assert b"outside-static-marker" not in body


def test_directory_index_symlink_cannot_escape_root(tmp_path):
    root = tmp_path / "site-root"
    directory = root / "page"
    directory.mkdir(parents=True)
    outside = tmp_path / "outside.html"
    outside.write_bytes(b"outside-static-marker")
    try:
        (directory / "index.html").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("File symlinks are unavailable on this host")
    status, _, body = _static(root, "/page/")
    assert status in {403, 404}
    assert b"outside-static-marker" not in body


@pytest.mark.parametrize("path", ["/site/index.html", "/site/", "/"])
def test_static_keeps_html_routes(tmp_path, path):
    site = tmp_path / "site"
    site.mkdir()
    expected = b"<!doctype html><title>Public</title>"
    (site / "index.html").write_bytes(expected)
    status, headers, body = _static(tmp_path, path)
    assert status == 200 and body == expected
    assert headers["Content-Type"].split(";")[0] == "text/html"


def test_static_keeps_existing_woff2_fonts():
    root = Path(__file__).resolve().parents[1]
    fonts = sorted((root / "site" / "assets" / "fonts").glob("*.woff2"))
    assert fonts
    for font in fonts:
        status, _, body = _static(root, "/" + font.relative_to(root).as_posix())
        assert status == 200 and body == font.read_bytes()


@pytest.mark.parametrize("relative,expected", [
    ("tasks/curated/hard_v2.jsonl", b'{"task":"fixture"}\n'),
    ("site/data.json", b'{"public":true}'),
    ("site/icon.svg", b'<svg xmlns="http://www.w3.org/2000/svg"/>'),
])
def test_static_keeps_supported_data_and_svg(tmp_path, relative, expected):
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(expected)
    status, _, body = _static(tmp_path, "/" + relative)
    assert status == 200 and body == expected


def _stub_provider(monkeypatch):
    calls = []

    class Provider:
        def generate(self, prompt, **kwargs):
            calls.append(("generate", kwargs["temperature"]))
            return ProposerOutput("reply", "stub", 0, "hash", "stub")

    def resolve(*args):
        calls.append(("resolve", args))
        return Provider(), None, 200

    def stats():
        calls.append(("stats", None))
        raise AssertionError("Invalid input must not access routing statistics")

    monkeypatch.setattr(gateway, "_resolve_proposer", resolve)
    monkeypatch.setattr(gateway, "get_router_stats", stats)
    return calls


INVALID_TEMPERATURES = [
    None, True, False, [], [0.5], {}, {"value": 0.5}, "invalid", "",
    float("nan"), float("inf"), float("-inf"), "NaN", "Infinity", "-Infinity",
    "1e10000", 10 ** 1000,
]
INVALID_IDS = [
    "null", "true", "false", "empty-list", "list", "empty-object", "object",
    "invalid-string", "empty-string", "nan", "inf", "negative-inf",
    "nan-string", "inf-string", "negative-inf-string", "overflow-string", "overflow-int",
]


@pytest.mark.parametrize("temperature", INVALID_TEMPERATURES, ids=INVALID_IDS)
def test_bad_temperature_returns_400_before_provider_or_stats(monkeypatch, temperature):
    calls = _stub_provider(monkeypatch)
    request = {"messages": [{"role": "user", "content": "hello"}],
               "temperature": temperature, "adaptive": True}
    body, status, receipt, text, model = gateway.openai_chat(request, "http://unused.invalid")
    assert status == 400 and body["error"]["type"] == "invalid_request_error"
    assert (receipt, text, model) == (None, None, None)
    assert calls == []


@pytest.mark.parametrize("temperature", [0, 0.5, -0.5, 1e308, "0.25", " 1 ", "-0.5"])
def test_finite_temperature_preserves_success(monkeypatch, temperature):
    calls = _stub_provider(monkeypatch)
    request = {"messages": [{"role": "user", "content": "hello"}],
               "temperature": temperature}
    body, status, receipt, text, model = gateway.openai_chat(request, "http://unused.invalid")
    assert status == 200 and body["choices"][0]["message"]["content"] == "reply"
    assert receipt and text == "reply" and model == "stub"
    assert calls[-1] == ("generate", float(temperature))


def test_omitted_temperature_preserves_default(monkeypatch):
    calls = _stub_provider(monkeypatch)
    request = {"messages": [{"role": "user", "content": "hello"}]}
    _, status, _, text, _ = gateway.openai_chat(request, "http://unused.invalid")
    assert status == 200 and text == "reply"
    assert calls[-1] == ("generate", 0.0)
