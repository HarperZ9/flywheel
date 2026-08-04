"""Falsifiers for the sign-in seam (harness/oauth_signin.py).

The covenant split: subscription_auth READS an authorized token; oauth_signin
is the explicit, operator-initiated login that WRITES it, under the exact name
the read-only resolver consumes. These pin what an adversarial review proved
the first draft lacked: a failed store is never reported as success, a
provider error never escapes as a traceback, no flow starts on a machine that
cannot keep the token, and no token value reaches any output.
"""
import base64
import hashlib
import io
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from contextlib import redirect_stdout

import pytest

import harness.oauth_signin as osi
from harness.subscription_auth import default_auth_resolver


@pytest.fixture
def store(monkeypatch):
    """A working credential store: available, and recording what it wrote."""
    written = {}
    monkeypatch.setattr(osi.keychain, "keychain_available", lambda: True)
    monkeypatch.setattr(osi.keychain, "keychain_set",
                        lambda name, value: written.update({name: value}) or {"stored": name})
    return written


def _fake_response(payload):
    class _R:
        def read(self):
            return json.dumps(payload).encode()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
    return _R()


def _approve(url, query="code=ok"):
    """Simulate the user approving: fetch the real callback URL this run
    published, with the nonce path the server chose."""
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    callback = (params.get("callback_url") or params.get("redirect_uri"))[0]
    threading.Timer(0.2, lambda: _get(f"{callback}?{query}")).start()
    return True


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return None


# --- PKCE math -------------------------------------------------------------

def test_pkce_challenge_is_s256_of_verifier():
    verifier, challenge = osi._pkce_pair()
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    assert challenge == base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    assert "=" not in challenge and len(verifier) >= 43


def test_pkce_pairs_are_unique():
    assert osi._pkce_pair() != osi._pkce_pair()


# --- storage truth (the high-severity finding) -----------------------------

def test_store_failure_is_never_reported_as_success(monkeypatch):
    monkeypatch.setattr(osi.keychain, "keychain_available", lambda: True)
    monkeypatch.setattr(osi.keychain, "keychain_set",
                        lambda n, v: {"error": "credential store write failed"})
    result = osi._store(osi.PROFILES["openrouter"], "sk-or-live")
    assert result["ok"] is False
    assert "NOT stored" in result["error"]
    assert "sk-or-live" not in json.dumps(result)


def test_no_flow_starts_without_a_credential_store(monkeypatch):
    # A token minted and then dropped is a live credential stranded at the
    # provider: refuse BEFORE the browser opens.
    monkeypatch.setattr(osi.keychain, "keychain_available", lambda: False)
    opened = []
    result = osi.login("openrouter", browser=lambda u: opened.append(u),
                       opener=lambda *a, **k: pytest.fail("exchanged anyway"))
    assert result["ok"] is False
    assert "could not be kept" in result["error"]
    assert opened == []


def test_logout_reports_an_env_token_it_cannot_clear(monkeypatch):
    monkeypatch.setattr(osi.keychain, "keychain_delete", lambda n: {"deleted": n})
    monkeypatch.setattr(osi.keychain, "credential_source", lambda n: "env")
    result = osi.logout("openrouter")
    assert result["ok"] is False
    assert "still set in the environment" in result["error"]


def test_logout_success_when_nothing_remains(monkeypatch):
    monkeypatch.setattr(osi.keychain, "keychain_delete", lambda n: {"deleted": n})
    monkeypatch.setattr(osi.keychain, "credential_source", lambda n: "absent")
    assert osi.logout("openrouter")["ok"] is True


# --- the wired flows -------------------------------------------------------

def test_openrouter_flow_stores_under_the_resolver_name(store):
    out = io.StringIO()
    with redirect_stdout(out):
        result = osi.login("openrouter", browser=_approve,
                           opener=lambda r, timeout=0: _fake_response({"key": "sk-or-tok"}),
                           timeout=15)
    assert result["ok"] is True and result["stored"] == "OPENROUTER_API_KEY"
    assert store == {"OPENROUTER_API_KEY": "sk-or-tok"}
    assert "sk-or-tok" not in out.getvalue() + json.dumps(result)
    assert "OPENROUTER_API_KEY" in default_auth_resolver().source("openrouter")


def test_openrouter_wire_shape_matches_the_documented_contract(store):
    seen = {}

    def _opener(request, timeout=0):
        seen["url"] = request.full_url
        seen["body"] = json.loads(request.data.decode())
        seen["ctype"] = request.headers.get("Content-type")
        return _fake_response({"key": "k"})

    def _browser(url):
        seen["authorize"] = url
        return _approve(url)

    with redirect_stdout(io.StringIO()):
        osi.login("openrouter", browser=_browser, opener=_opener, timeout=15)
    q = urllib.parse.parse_qs(urllib.parse.urlparse(seen["authorize"]).query)
    assert set(q) == {"callback_url", "code_challenge", "code_challenge_method"}
    assert q["code_challenge_method"] == ["S256"]
    assert seen["url"] == "https://openrouter.ai/api/v1/auth/keys"
    assert set(seen["body"]) == {"code", "code_verifier", "code_challenge_method"}
    assert seen["ctype"] == "application/json"


def test_registered_flow_uses_standard_oauth2_wire(monkeypatch, store):
    monkeypatch.setenv("FLYWHEEL_OPENAI_OAUTH_CLIENT_ID", "client-123")
    monkeypatch.setenv("FLYWHEEL_OPENAI_OAUTH_AUTHORIZE_URL", "https://auth.example/authorize")
    monkeypatch.setenv("FLYWHEEL_OPENAI_OAUTH_EXCHANGE_URL", "https://auth.example/token")
    seen = {}

    def _opener(request, timeout=0):
        seen["url"] = request.full_url
        seen["body"] = urllib.parse.parse_qs(request.data.decode())
        seen["ctype"] = request.headers.get("Content-type")
        return _fake_response({"access_token": "at-xyz"})

    def _browser(url):
        seen["authorize"] = url
        return _approve(url)

    with redirect_stdout(io.StringIO()):
        result = osi.login("openai", browser=_browser, opener=_opener, timeout=15)
    assert result["ok"] is True and store["CHATGPT_OAUTH_TOKEN"] == "at-xyz"
    q = urllib.parse.parse_qs(urllib.parse.urlparse(seen["authorize"]).query)
    assert q["response_type"] == ["code"] and q["client_id"] == ["client-123"]
    assert "redirect_uri" in q and q["code_challenge_method"] == ["S256"]
    assert "state" in q
    assert seen["ctype"] == "application/x-www-form-urlencoded"
    assert seen["body"]["grant_type"] == ["authorization_code"]
    assert seen["body"]["client_id"] == ["client-123"]
    assert "code_verifier" in seen["body"]


def test_registered_flow_refuses_without_the_operator_client_id(monkeypatch):
    monkeypatch.delenv("FLYWHEEL_OPENAI_OAUTH_CLIENT_ID", raising=False)

    def _never(*a, **k):
        raise AssertionError("no browser or network without a client id")

    result = osi.login("openai", browser=_never, opener=_never)
    assert result["ok"] is False and "registration" in result["error"]


def test_registered_flow_refuses_without_endpoints(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_OPENAI_OAUTH_CLIENT_ID", "client-123")
    monkeypatch.delenv("FLYWHEEL_OPENAI_OAUTH_AUTHORIZE_URL", raising=False)
    monkeypatch.delenv("FLYWHEEL_OPENAI_OAUTH_EXCHANGE_URL", raising=False)
    result = osi.login("openai", browser=lambda u: True)
    assert result["ok"] is False and "_AUTHORIZE_URL" in result["error"]


def test_no_profile_carries_a_borrowed_client_id():
    # The honesty invariant, checked behaviorally rather than by grepping
    # source: no profile ships a client id; a registered flow gets one only
    # from the operator's environment.
    for profile in osi.PROFILES.values():
        assert profile.client_id == ""


# --- error paths never escape as tracebacks --------------------------------

def test_exchange_http_error_becomes_an_error_dict(store):
    def _raise(request, timeout=0):
        raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, None)

    with redirect_stdout(io.StringIO()):
        result = osi.login("openrouter", browser=_approve, opener=_raise, timeout=15)
    assert result["ok"] is False and "HTTP 400" in result["error"]
    assert store == {}


def test_exchange_network_error_becomes_an_error_dict(store):
    def _raise(request, timeout=0):
        raise urllib.error.URLError("connection refused")

    with redirect_stdout(io.StringIO()):
        result = osi.login("openrouter", browser=_approve, opener=_raise, timeout=15)
    assert result["ok"] is False and "URLError" in result["error"]
    assert store == {}


def test_response_without_a_token_field_stores_nothing(store):
    with redirect_stdout(io.StringIO()):
        result = osi.login("openrouter", browser=_approve,
                           opener=lambda r, timeout=0: _fake_response({"error": "denied"}),
                           timeout=15)
    assert result["ok"] is False and "no token field" in result["error"]
    assert store == {}


def test_denied_callback_stores_nothing(store):
    with redirect_stdout(io.StringIO()):
        result = osi.login(
            "openrouter",
            browser=lambda u: _approve(u, query="error=access_denied"),
            opener=lambda *a, **k: pytest.fail("exchanged after a denial"),
            timeout=15)
    assert result["ok"] is False and "access_denied" in result["error"]
    assert store == {}


# --- guided flow and redaction ---------------------------------------------

def test_no_token_value_in_any_guided_output(store):
    out = io.StringIO()
    with redirect_stdout(out):
        result = osi._login_guided(osi.PROFILES["anthropic"],
                                   prompt=lambda _: "sk-ant-oat-SECRET-VALUE")
    text = out.getvalue() + json.dumps(result)
    assert "SECRET-VALUE" not in text
    assert result["ok"] is True and result["stored"] == "CLAUDE_CODE_OAUTH_TOKEN"
    assert result["sha256"] == hashlib.sha256(b"sk-ant-oat-SECRET-VALUE").hexdigest()[:12]


def test_guided_empty_paste_stores_nothing(store):
    with redirect_stdout(io.StringIO()):
        result = osi._login_guided(osi.PROFILES["anthropic"], prompt=lambda _: "   ")
    assert result["ok"] is False and store == {}


# --- resolver wiring and the CLI -------------------------------------------

def test_unknown_provider_is_a_named_error():
    assert osi.login("nonesuch")["ok"] is False
    assert osi.logout("nonesuch")["ok"] is False


def test_status_reports_presence_never_values(monkeypatch):
    monkeypatch.setattr(osi.keychain, "resolve_credential",
                        lambda n: "tok-value" if n == "OPENROUTER_API_KEY" else "")
    monkeypatch.setattr(osi.keychain, "credential_source",
                        lambda n: "keychain" if n == "OPENROUTER_API_KEY" else "absent")
    rows = osi.status()
    assert "tok-value" not in json.dumps(rows)
    by_name = {r["provider"]: r for r in rows}
    assert by_name["openrouter"]["present"] is True
    assert by_name["anthropic"]["present"] is False
    assert all(r["sanction"] for r in rows)


def test_auth_cli_status_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr(osi.keychain, "resolve_credential", lambda n: "")
    monkeypatch.setattr(osi.keychain, "credential_source", lambda n: "absent")
    assert osi.cli(["status"]) == 0
    out = capsys.readouterr().out
    assert "openrouter" in out and "anthropic" in out and "openai" in out


def test_auth_cli_usage_on_bad_args():
    assert osi.cli(["login"]) == 2
