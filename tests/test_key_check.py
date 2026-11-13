"""Falsifiers for the key test at setup: one read-only request, the key in a
header only, a redacted one-line answer, and nothing stored unless the
provider said yes. Every transport here is a fake; no socket is opened."""
import io
import urllib.error

import pytest

from harness import accounts, key_check, keychain, setup_cli

KEY = "sk-" + "ant-" + "k" * 40
ODD_KEY = "zz" + "Q7" * 20            # a shape no redaction pattern knows


def _transport(status, body=None, seen=None):
    def send(url, headers, timeout):
        if seen is not None:
            seen.append((url, dict(headers), timeout))
        return status, {}, body or {}
    return send


@pytest.mark.parametrize("provider", sorted(key_check.ROUTES))
def test_one_read_only_request_with_the_key_in_a_header_only(provider):
    seen = []
    ok, line = key_check.check_key(provider, KEY, transport=_transport(200, seen=seen))
    assert ok is True and line == f"the key works ({provider} accepted it)"
    assert len(seen) == 1
    url, headers, _ = seen[0]
    assert url.startswith("https://") and KEY not in url and "?" not in url
    assert url.endswith(("/models", "/key")), "a listing, never a completion"
    assert any(KEY in value for value in headers.values())


def test_every_setup_provider_has_a_route():
    assert set(key_check.ROUTES) == set(setup_cli.PROVIDERS)


def test_a_rejected_key_gives_the_providers_reason_without_the_key():
    body = {"error": {"type": "authentication_error",
                      "message": f"invalid x-api-key: {KEY}"}}
    ok, line = key_check.check_key("anthropic", KEY, transport=_transport(401, body))
    assert ok is False and "\n" not in line
    assert "401" in line and "the key was not accepted" in line
    assert KEY not in line and KEY[-12:] not in line


def test_a_key_of_unknown_shape_is_still_removed_from_the_line():
    body = {"error": {"message": f"Incorrect API key provided: {ODD_KEY}"}}
    ok, line = key_check.check_key("openai", ODD_KEY, transport=_transport(401, body))
    assert ok is False and ODD_KEY not in line


def test_no_answer_is_reported_as_untested():
    def down(url, headers, timeout):
        raise urllib.error.URLError("no route")
    ok, line = key_check.check_key("openai", KEY, transport=down)
    assert ok is None and "could not reach openai" in line and KEY not in line


def test_the_default_transport_turns_an_http_error_into_an_answer(monkeypatch):
    def refuse(request, timeout):
        assert request.get_method() == "GET" and request.data is None
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {},
                                     io.BytesIO(b'{"error": {"message": "no access"}}'))
    monkeypatch.setattr(key_check._OPENER, "open", refuse)
    ok, line = key_check.check_key("deepseek", KEY)
    assert ok is False and "403" in line and KEY not in line


def test_redirects_are_refused():
    handler = key_check._NoRedirect()
    assert handler.redirect_request(None, None, 302, "Found", {}, "https://elsewhere") is None


class _Store:
    def __init__(self):
        self.items = {}

    def get(self, name):
        return self.items.get(name)

    def set(self, name, secret):
        self.items[name] = secret
        return {"stored": name}

    def delete(self, name):
        return {"deleted": name} if self.items.pop(name, None) else {"error": "missing"}


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setattr(keychain, "keychain_available", lambda: True)
    return _Store()


def _run(store, tmp_path, check):
    return setup_cli.store("anthropic", read_secret=lambda prompt: KEY, check=check,
                           store_backend=store, index=tmp_path / "accounts.json")


def test_setup_stores_only_a_key_the_provider_accepted(store, tmp_path):
    ok, message = _run(store, tmp_path, lambda p, k: (False, "the key was not accepted: 401"))
    assert not ok and store.items == {} and "--no-check" in message
    assert not (tmp_path / "accounts.json").exists()
    ok, message = _run(store, tmp_path, lambda p, k: (None, "could not reach anthropic"))
    assert not ok and store.items == {} and "Nothing was stored" in message
    ok, message = _run(store, tmp_path, lambda p, k: (True, "the key works"))
    assert ok and store.items == {"ANTHROPIC_API_KEY": KEY}
    assert message.startswith("the key works\n") and KEY not in message


def test_no_check_stores_without_asking_the_provider(store, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(accounts, "KeychainStore", lambda: store)
    monkeypatch.setattr(setup_cli.getpass, "getpass", lambda prompt: KEY)
    monkeypatch.setattr(key_check, "check_key",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("checked")))
    assert setup_cli.main(["--provider", "anthropic", "--no-check"]) == 0
    assert store.items == {"ANTHROPIC_API_KEY": KEY}
    assert KEY not in capsys.readouterr().out


def test_setup_checks_by_default_and_fails_closed(store, monkeypatch, capsys):
    monkeypatch.setattr(accounts, "KeychainStore", lambda: store)
    monkeypatch.setattr(setup_cli.getpass, "getpass", lambda prompt: KEY)
    monkeypatch.setattr(key_check, "check_key", lambda p, k: (False, "the key was not accepted"))
    assert setup_cli.main(["--provider", "openai"]) == 1
    captured = capsys.readouterr()
    assert store.items == {} and "the key was not accepted" in captured.err
    assert KEY not in captured.out + captured.err
