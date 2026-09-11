"""Anthropic native model roster listing.

These tests catch false success modes that matter to the picker: a configured
fallback default is not provider data, provider catalog presence is not inference
availability, unsafe provider strings must not become selectable model ids, and
credential handling must stay internal and sanitized.
"""
import json
import urllib.parse

import harness.model_roster as MR


class _Resp:
    def __init__(self, payload=None, raw=None):
        self._payload = payload
        self._raw = raw

    def read(self, size=-1):
        if self._raw is not None:
            return self._raw if size is None or size < 0 else self._raw[:size]
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _forbid_claude_cli_probe(monkeypatch):
    import harness.endpoint_registry as endpoint_registry

    def boom():
        raise AssertionError("model roster must not probe Claude CLI auth")

    monkeypatch.setattr(endpoint_registry.claude_cli_auth, "public_status", boom)


def test_anthropic_lists_provider_models_without_cli_probe(monkeypatch):
    # Would fail if Anthropic stayed on the native default-only path, if it used
    # unified_roster and reached Claude CLI auth, or if the configured default was
    # treated as provider-listed data when absent from the API response.
    _forbid_claude_cli_probe(monkeypatch)
    monkeypatch.setattr(MR, "_credential", lambda name: "sk-" + "ant-test")
    captured = {}

    def fake_open(req, timeout):
        captured["url"] = req.full_url
        headers = {k.lower(): v for k, v in req.header_items()}
        captured["key"] = headers.get("x-api-key")
        captured["version"] = headers.get("anthropic-version")
        return _Resp({
            "data": [
                {"type": "model", "id": "claude-opus-5", "capabilities": None},
                {"type": "model", "id": "claude-haiku-5", "capabilities": {"thinking": {"supported": True}}},
            ],
            "has_more": False,
            "last_id": "claude-haiku-5",
        })

    monkeypatch.setattr(MR, "_open_anthropic", fake_open, raising=False)
    out = MR.list_models("anthropic")
    assert captured == {
        "url": "https://api.anthropic.com/v1/models?limit=100",
        "key": "sk-" + "ant-test",
        "version": "2023-06-01",
    }
    assert out["models"] == [
        {"id": "claude-sonnet-5", "default": "true"},
        {"id": "claude-opus-5", "default": "false"},
        {"id": "claude-haiku-5", "default": "false"},
    ]
    assert out["provider_listed_models"] == ["claude-opus-5", "claude-haiku-5"]
    assert out["default_model_source"] == "configured"
    assert out["default_provider_listed"] is False
    assert out["availability"] == "provider_catalog_only"
    assert "not listed" in out["reason"]


def test_anthropic_paginates_with_after_id_and_total_page_cap(monkeypatch):
    # Would fail if pagination silently stopped at the first provider page or if
    # a server loop could make the picker wait without a page bound.
    monkeypatch.setattr(MR, "_credential", lambda name: "sk-" + "ant-test")
    pages = [
        {"data": [{"id": "claude-a"}], "has_more": True, "last_id": "claude-a"},
        {"data": [{"id": "claude-b"}], "has_more": False, "last_id": "claude-b"},
    ]
    urls = []

    def fake_open(req, timeout):
        urls.append(req.full_url)
        return _Resp(pages.pop(0))

    monkeypatch.setattr(MR, "_open_anthropic", fake_open, raising=False)
    out = MR.list_models("anthropic")
    parsed = [urllib.parse.parse_qs(urllib.parse.urlsplit(u).query) for u in urls]
    assert parsed == [{"limit": ["100"]}, {"limit": ["100"], "after_id": ["claude-a"]}]
    assert out["provider_listed_models"] == ["claude-a", "claude-b"]


def test_anthropic_refuses_unsafe_cursor_before_next_request(monkeypatch):
    # Would fail if a provider-supplied cursor could be reflected into the next
    # request after_id, including strings shaped like credentials.
    monkeypatch.setattr(MR, "_credential", lambda name: "sk-" + "ant-test")
    calls = []

    def fake_open(req, timeout):
        calls.append(req.full_url)
        return _Resp({
            "data": [{"id": "claude-a"}],
            "has_more": True,
            "last_id": "sk-" + "ant-oat-secret-shaped-cursor",
        })

    monkeypatch.setattr(MR, "_open_anthropic", fake_open, raising=False)
    out = MR.list_models("anthropic")
    assert len(calls) == 1
    assert out["provider_listed_models"] == ["claude-a"]
    assert "invalid cursor" in out["reason"]


def test_anthropic_oversize_response_falls_back_without_secret_echo(monkeypatch):
    # Would fail if the lister read an unbounded response body, or if an error
    # that contained a key-shaped string was echoed into the UI reason.
    monkeypatch.setattr(MR, "_credential", lambda name: "sk-" + "ant-test")
    monkeypatch.setattr(MR, "_ANTHROPIC_MAX_RESPONSE_BYTES", 16, raising=False)

    def fake_open(req, timeout):
        return _Resp(raw=b'{"error":"' + b'sk-' + b'ant-oat-SECRET"}' * 4)

    monkeypatch.setattr(MR, "_open_anthropic", fake_open, raising=False)
    out = MR.list_models("anthropic")
    assert out["models"] == [{"id": "claude-sonnet-5", "default": "true"}]
    assert "response too large" in out["reason"]
    assert "sk-ant" not in json.dumps(out)


def test_anthropic_skips_secret_shaped_and_oversize_model_ids(monkeypatch):
    # Would fail if provider data were copied into selectable model IDs before
    # applying the same bounded-safe-ID policy used by model overrides.
    monkeypatch.setattr(MR, "_credential", lambda name: "sk-" + "ant-test")
    too_long = "c" * 161

    def fake_open(req, timeout):
        return _Resp({
            "data": [
                {"id": "sk-" + "ant-oat-secret-shaped-model"},
                {"id": too_long},
                {"id": "claude-valid-5"},
            ],
            "has_more": False,
            "last_id": "claude-valid-5",
        })

    monkeypatch.setattr(MR, "_open_anthropic", fake_open, raising=False)
    out = MR.list_models("anthropic")
    assert out["provider_listed_models"] == ["claude-valid-5"]
    encoded = json.dumps(out)
    assert "sk-ant" not in encoded and too_long not in encoded


def test_anthropic_credential_absent_does_not_probe_http_or_cli(monkeypatch):
    # Would fail if an absent API key still touched the network or fell through
    # to unified_roster/Claude CLI status probing.
    _forbid_claude_cli_probe(monkeypatch)
    monkeypatch.setattr(MR, "_credential", lambda name: "")
    monkeypatch.setattr(
        MR, "_open_anthropic",
        lambda req, timeout: (_ for _ in ()).throw(AssertionError("no HTTP without credential")),
        raising=False,
    )
    out = MR.list_models("anthropic")
    assert out["models"] == [{"id": "claude-sonnet-5", "default": "true"}]
    assert out["reason"] == "credential absent"
    assert out["default_model_source"] == "configured"
    assert out["default_provider_listed"] is None


def test_anthropic_listing_error_is_sanitized(monkeypatch):
    # Would fail if exception text with key-shaped data reached the picker.
    monkeypatch.setattr(MR, "_credential", lambda name: "sk-" + "ant-test")

    def fake_open(req, timeout):
        raise OSError("upstream included " + "sk-" + "ant-oat-SECRET in an error")

    monkeypatch.setattr(MR, "_open_anthropic", fake_open, raising=False)
    out = MR.list_models("anthropic")
    assert out["models"] == [{"id": "claude-sonnet-5", "default": "true"}]
    assert out["reason"] == "listing unavailable: OSError"
    assert "sk-ant" not in json.dumps(out)


def test_anthropic_page_cap_returns_truncated_reason(monkeypatch):
    # Would fail if has_more=True could keep paging past Flywheel's local cap.
    monkeypatch.setattr(MR, "_credential", lambda name: "sk-" + "ant-test")
    monkeypatch.setattr(MR, "_ANTHROPIC_MAX_PAGES", 2)
    calls = []

    def fake_open(req, timeout):
        calls.append(req.full_url)
        return _Resp({
            "data": [{"id": f"claude-page-{len(calls)}"}],
            "has_more": True,
            "last_id": f"claude-page-{len(calls)}",
        })

    monkeypatch.setattr(MR, "_open_anthropic", fake_open, raising=False)
    out = MR.list_models("anthropic")
    assert len(calls) == 2
    assert out["provider_listed_models"] == ["claude-page-1", "claude-page-2"]
    assert "page cap" in out["reason"]


def test_anthropic_opener_disables_proxy_and_redirect(monkeypatch):
    # Would fail if x-api-key requests used ambient proxy settings or default
    # redirect handling, either of which could forward credentials off-origin.
    captured = {}

    class _Opener:
        def open(self, req, timeout):
            captured["url"] = req.full_url
            captured["timeout"] = timeout
            return _Resp({"data": [], "has_more": False})

    def fake_build_opener(*handlers):
        captured["handlers"] = handlers
        return _Opener()

    monkeypatch.setattr(MR.urllib.request, "build_opener", fake_build_opener)
    req = MR.urllib.request.Request("https://api.anthropic.com/v1/models?limit=100")
    with MR._open_anthropic(req, 1.25) as resp:
        assert resp.read()
    handlers = captured["handlers"]
    assert any(isinstance(h, MR._NoRedirect) for h in handlers)
    proxy_handlers = [h for h in handlers if isinstance(h, MR.urllib.request.ProxyHandler)]
    assert proxy_handlers and proxy_handlers[0].proxies == {}
    assert captured["timeout"] == 1.25
