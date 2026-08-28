"""Falsifiers for the GUI-shaped sign-in seam (harness/oauth_service.py).

A browser flow cannot block an HTTP request and a hidden stdin paste cannot
happen over HTTP, so this module adapts both. What must NOT change in the
adaptation: no token value in any roster or job record, a paste is accepted
only for the provider whose flow actually works that way, and a machine with
no credential store refuses before anything is minted.
"""
import json
import time

import harness.oauth_service as svc


def _settle(provider, timeout=5.0):
    """Wait for the background sign-in thread to finish."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if svc._job(provider).get("state") != "running":
            return svc._job(provider)
        time.sleep(0.02)
    return svc._job(provider)


def _clear_jobs():
    with svc._LOCK:
        svc._JOBS.clear()


def test_roster_carries_terms_and_never_a_value(monkeypatch):
    monkeypatch.setattr(svc.keychain, "resolve_credential",
                        lambda n: "tok-secret" if n == "OPENROUTER_API_KEY" else "")
    monkeypatch.setattr(svc.keychain, "credential_source",
                        lambda n: "keychain" if n == "OPENROUTER_API_KEY" else "absent")
    doc = svc.auth_rows()
    assert "tok-secret" not in json.dumps(doc)
    by = {r["provider"]: r for r in doc["providers"]}
    assert by["openrouter"]["present"] is True
    assert by["anthropic"]["present"] is False
    # every row states its terms, so the surface never has to invent them
    assert all(r["sanction"] and r["kind_label"] for r in doc["providers"])


def test_guided_provider_returns_steps_instead_of_running_a_flow(monkeypatch):
    monkeypatch.setattr(svc.keychain, "keychain_available", lambda: True)
    monkeypatch.setattr(svc.oauth_signin, "login",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("guided must not run a browser flow")))
    out = svc.begin("anthropic")
    assert out["ok"] is True and out["mode"] == "guided"
    assert len(out["steps"]) >= 2
    assert out["keychain_name"] == "CLAUDE_CODE_OAUTH_TOKEN"


def test_browser_flow_returns_at_once_and_reports_through_the_roster(monkeypatch):
    _clear_jobs()
    monkeypatch.setattr(svc.keychain, "keychain_available", lambda: True)
    started = []

    def _slow_login(provider, **kwargs):
        started.append(provider)
        time.sleep(0.05)
        return {"ok": True, "provider": provider, "stored": "OPENROUTER_API_KEY"}

    monkeypatch.setattr(svc.oauth_signin, "login", _slow_login)
    t0 = time.time()
    out = svc.begin("openrouter")
    assert out["ok"] is True and out["mode"] == "browser"
    assert time.time() - t0 < 0.05        # returned before the flow finished
    assert _settle("openrouter").get("state") == "done"
    assert started == ["openrouter"]


def test_a_failed_browser_flow_surfaces_its_error(monkeypatch):
    _clear_jobs()
    monkeypatch.setattr(svc.keychain, "keychain_available", lambda: True)
    monkeypatch.setattr(svc.oauth_signin, "login",
                        lambda p, **k: {"ok": False, "provider": p,
                                        "error": "token exchange rejected (HTTP 400)"})
    svc.begin("openrouter")
    job = _settle("openrouter")
    assert job["state"] == "failed" and "HTTP 400" in job["error"]
    monkeypatch.setattr(svc.keychain, "resolve_credential", lambda n: "")
    monkeypatch.setattr(svc.keychain, "credential_source", lambda n: "absent")
    row = {r["provider"]: r for r in svc.auth_rows()["providers"]}["openrouter"]
    assert row["last"] == "failed" and "HTTP 400" in row["last_error"]


def test_a_raised_flow_never_leaks_a_body(monkeypatch):
    _clear_jobs()
    monkeypatch.setattr(svc.keychain, "keychain_available", lambda: True)

    def _boom(provider, **kwargs):
        raise RuntimeError("secret-token-in-message")

    monkeypatch.setattr(svc.oauth_signin, "login", _boom)
    svc.begin("openrouter")
    job = _settle("openrouter")
    assert job["state"] == "failed"
    assert "secret-token-in-message" not in job["error"]
    assert "RuntimeError" in job["error"]


def test_nothing_starts_without_a_credential_store(monkeypatch):
    monkeypatch.setattr(svc.keychain, "keychain_available", lambda: False)
    monkeypatch.setattr(svc.oauth_signin, "login",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("must not mint what it cannot keep")))
    out = svc.begin("openrouter")
    assert out["ok"] is False and out["mode"] == "unavailable"


def test_paste_is_accepted_only_for_a_guided_provider(monkeypatch):
    stored = {}
    monkeypatch.setattr(svc.oauth_signin.keychain, "keychain_set",
                        lambda n, v: stored.update({n: v}) or {"stored": n})
    ok = svc.submit("anthropic", "  sk-ant-oat-VALUE  ")
    assert ok["ok"] is True and stored == {"CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-oat-VALUE"}
    assert "sk-ant-oat-VALUE" not in json.dumps(ok)
    # a browser provider must not accept a value it did not obtain itself
    bad = svc.submit("openrouter", "sk-or-pasted")
    assert bad["ok"] is False and "not a paste" in bad["error"]
    assert "OPENROUTER_API_KEY" not in stored


def test_empty_paste_stores_nothing(monkeypatch):
    monkeypatch.setattr(svc.oauth_signin.keychain, "keychain_set",
                        lambda n, v: (_ for _ in ()).throw(
                            AssertionError("stored an empty paste")))
    assert svc.submit("anthropic", "   ")["ok"] is False


def test_unknown_provider_is_named_on_every_verb():
    assert svc.begin("nonesuch")["ok"] is False
    assert svc.submit("nonesuch", "x")["ok"] is False
    assert svc.sign_out("nonesuch")["ok"] is False


def test_remote_pkce_returns_the_url_and_advertises_the_reached_host(monkeypatch):
    # A paired phone sends the engine address it reached as callback_base. The
    # browser flow returns the authorize URL for the phone to open, and the
    # callback listener advertises that same address, not loopback.
    _clear_jobs()
    monkeypatch.setattr(svc.keychain, "keychain_available", lambda: True)
    seen = {}

    def _fake_begin(profile, advertise_host=None):
        seen["host"] = advertise_host
        return (object(), "http://10.0.0.5:55555/cb/n", "verifier",
                "https://openrouter.ai/auth?callback_url=http%3A%2F%2F10.0.0.5")

    def _fake_finish(profile, server, callback, verifier, **k):
        return {"ok": True, "provider": profile.provider,
                "stored": "OPENROUTER_API_KEY"}

    monkeypatch.setattr(svc.oauth_signin, "_pkce_begin", _fake_begin)
    monkeypatch.setattr(svc.oauth_signin, "_pkce_finish", _fake_finish)
    out = svc.begin("openrouter", callback_base="http://10.0.0.5:8799")
    assert out["ok"] is True and out["mode"] == "browser"
    assert out["authorize_url"].startswith("https://openrouter.ai/auth")
    assert seen["host"] == "10.0.0.5"        # the reached engine, not loopback
    assert _settle("openrouter").get("state") == "done"


def test_local_pkce_returns_no_authorize_url(monkeypatch):
    # Without callback_base the browser opens on the engine itself, so there is
    # no URL to hand back and the loopback path is untouched.
    _clear_jobs()
    monkeypatch.setattr(svc.keychain, "keychain_available", lambda: True)
    monkeypatch.setattr(svc.oauth_signin, "login",
                        lambda p, **k: {"ok": True, "provider": p})
    out = svc.begin("openrouter")
    assert "authorize_url" not in out
    _settle("openrouter")


def test_remote_pkce_refuses_an_unreadable_callback_base(monkeypatch):
    # A callback_base with no host cannot be returned to; refuse before any
    # listener is stood up rather than silently falling back to loopback.
    _clear_jobs()
    monkeypatch.setattr(svc.keychain, "keychain_available", lambda: True)
    monkeypatch.setattr(svc.oauth_signin, "_pkce_begin",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("must not build a listener with no host")))
    out = svc.begin("openrouter", callback_base="not-a-url")
    assert out["ok"] is False and "engine address" in out["error"]


def test_sign_out_clears_the_job_record(monkeypatch):
    _clear_jobs()
    svc._set_job("openrouter", "failed", "some error")
    monkeypatch.setattr(svc.oauth_signin, "logout",
                        lambda p: {"provider": p, "ok": True, "cleared": "X"})
    assert svc.sign_out("openrouter")["ok"] is True
    assert svc._job("openrouter") == {}
