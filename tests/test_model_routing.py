"""Falsifiers for model-neutral routing with failover.

Two real things proven:
  1. the Anthropic /v1/messages wire actually hits that endpoint shape (live mock),
     the protocol the OpenAI-wire proposer does not speak;
  2. the router fails over across providers on 429/quota, unreachable, and
     absent-auth, records the trace in a receipt that carries no secret, and
     plugs into the same accept path as any proposer.
"""
from __future__ import annotations

import json
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from harness.model_router import (FLAGSHIP, Attempt, Candidate, RoutingExhausted,
                                   RoutingProposer, build_candidate, candidate,
                                   chain_for_role, retryable_status, route_role)
from harness.proposer import AnthropicProposer, EnterpriseProposer, ProposerOutput, prompt_hash

CORRECT = "def add(a, b):\n    return a + b\n"


# --- the Anthropic wire is real (live mock /v1/messages) --------------------

class _MockAnthropic(BaseHTTPRequestHandler):
    seen: list[dict] = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _MockAnthropic.seen.append({
            "path": self.path, "body": body,
            "x_api_key": self.headers.get("x-api-key", ""),
            "version": self.headers.get("anthropic-version", "")})
        out = json.dumps({"model": "claude-opus-5", "content": [
            {"type": "text", "text": "```python\ndef add(a, b):\n    return a + b\n```"}]})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out.encode())

    def log_message(self, *a):
        pass


@pytest.fixture
def anthropic_mock():
    _MockAnthropic.seen = []
    srv = HTTPServer(("127.0.0.1", 0), _MockAnthropic)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_anthropic_wire_hits_messages_endpoint(anthropic_mock, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    p = AnthropicProposer(base_url=anthropic_mock, model="claude-opus-5")
    out = p.generate("write add", seed=1, temperature=0.0, max_new_tokens=64,
                     system="be terse")
    (req,) = _MockAnthropic.seen
    assert req["path"] == "/v1/messages"
    assert req["x_api_key"] == "sk-test"
    assert req["version"] == "2023-06-01"
    assert req["body"]["system"] == "be terse"          # anthropic top-level system
    assert req["body"]["messages"][0]["role"] == "user"
    assert "seed" not in req["body"]                     # anthropic has no seed
    assert out.text == CORRECT                           # fences stripped
    assert out.served_model == "claude-opus-5"


# --- fake proposers for router tests (no network) ---------------------------

def _canned(text=CORRECT, served="fake"):
    class P:
        model_ref = "fake"
        def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
            return ProposerOutput(text=text, model_ref="fake", seed=seed,
                                  prompt_hash=prompt_hash(prompt), cache="miss",
                                  served_model=served)
    return P()


def _raises(code):
    class P:
        model_ref = "fake"
        def generate(self, *a, **k):
            raise urllib.error.HTTPError("http://x", code, "err", {}, None)
    return P()


def _unreachable():
    class P:
        model_ref = "fake"
        def generate(self, *a, **k):
            raise urllib.error.URLError("no route")
    return P()


def _c(provider, key_env=""):
    return Candidate(provider, "m", "openai", key_env, "")


# --- routing behavior --------------------------------------------------------

def test_retryable_status_classification():
    assert retryable_status(429) and retryable_status(503)
    assert not retryable_status(400) and not retryable_status(401)


def test_first_candidate_wins():
    r = RoutingProposer([_c("p1"), _c("p2")], builder=lambda c: _canned())
    out = r.generate("x", seed=0, temperature=0.0, max_new_tokens=8)
    assert out.model_ref == "p1:m"
    assert r.last_route.failover_count() == 0


def test_failover_on_429():
    builder = lambda c: _raises(429) if c.provider == "p1" else _canned(served="p2srv")
    r = RoutingProposer([_c("p1"), _c("p2")], builder=builder)
    out = r.generate("x", seed=0, temperature=0.0, max_new_tokens=8)
    assert out.model_ref == "p2:m"
    assert out.served_model == "p2srv"
    outcomes = [a.outcome for a in r.last_route.attempts]
    assert outcomes == ["failover", "ok"]
    assert r.last_route.failover_count() == 1


def test_failover_on_unreachable():
    builder = lambda c: _unreachable() if c.provider == "p1" else _canned()
    r = RoutingProposer([_c("p1"), _c("p2")], builder=builder)
    r.generate("x", seed=0, temperature=0.0, max_new_tokens=8)
    assert r.last_route.attempts[0].outcome == "unreachable"


def test_non_retryable_error_still_tries_next():
    # a 401 on one provider (bad key) should not kill the chain
    builder = lambda c: _raises(401) if c.provider == "p1" else _canned()
    r = RoutingProposer([_c("p1"), _c("p2")], builder=builder)
    out = r.generate("x", seed=0, temperature=0.0, max_new_tokens=8)
    assert out.model_ref == "p2:m"
    assert r.last_route.attempts[0].outcome == "error"


def test_absent_auth_is_skipped_without_calling(monkeypatch):
    monkeypatch.delenv("MISSING_KEY_ABC", raising=False)
    def builder(c):
        if c.provider == "needs_key":
            raise AssertionError("must not build a candidate whose key is absent")
        return _canned()
    r = RoutingProposer([_c("needs_key", key_env="MISSING_KEY_ABC"), _c("local")],
                        builder=builder)
    out = r.generate("x", seed=0, temperature=0.0, max_new_tokens=8)
    assert out.model_ref == "local:m"
    assert r.last_route.attempts[0].outcome == "auth_absent"


def test_exhaustion_raises_with_attempts():
    r = RoutingProposer([_c("p1"), _c("p2")], builder=lambda c: _raises(429))
    with pytest.raises(RoutingExhausted) as e:
        r.generate("x", seed=0, temperature=0.0, max_new_tokens=8)
    assert len(e.value.attempts) == 2
    assert all(a.outcome == "failover" for a in e.value.attempts)


# --- the routing receipt carries no secret ----------------------------------

def test_routing_receipt_shape_and_no_secret():
    builder = lambda c: _raises(429) if c.provider == "p1" else _canned()
    r = RoutingProposer([_c("p1"), _c("p2")], builder=builder)
    r.generate("x", seed=0, temperature=0.0, max_new_tokens=8)
    rec = r.last_route.to_receipt()
    assert rec["schema"] == "flywheel.routing-receipt/v1"
    assert rec["winner"] == "p2:m"
    assert rec["failover_count"] == 1
    assert len(rec["digest"]) == 16
    dumped = json.dumps(rec)
    for a in rec["attempts"]:
        assert a["auth_source"] in ("env", "keychain", "absent", "none")
    assert "sk-" not in dumped and "Bearer" not in dumped


# --- chain construction + dispatch ------------------------------------------

def test_flagship_chain_is_anthropic_first():
    chain = chain_for_role(FLAGSHIP)
    assert chain[0].provider == "anthropic"
    assert chain[0].model == "claude-fable-5"    # catalog: fable-5 is flagship
    assert chain[0].wire == "anthropic"
    assert len(chain) >= 2


def test_build_candidate_dispatches_wire():
    assert isinstance(build_candidate(candidate("anthropic")), AnthropicProposer)
    assert isinstance(build_candidate(candidate("deepseek")), EnterpriseProposer)


def test_route_role_constructs():
    # skip_absent_auth off so the injected builder is exercised regardless of
    # which provider keys happen to be configured in the test environment.
    r = route_role(FLAGSHIP, builder=lambda c: _canned(), skip_absent_auth=False)
    assert r.model_ref == "route:flagship"
    out = r.generate("x", seed=0, temperature=0.0, max_new_tokens=8)
    assert out.model_ref.startswith("anthropic:")


def test_role_chain_all_absent_auth_exhausts_cleanly(monkeypatch):
    # With no provider credential reachable, a role route fails over through
    # every candidate and exhausts honestly rather than pretending to answer.
    # The environment is one of two places the router looks. Clearing it is
    # half the setup, because on a machine whose OS keychain holds a provider
    # key the first candidate resolves, calls out, and the failure gets read as
    # a routing defect when it is really a fact about that machine.
    for env in ("ANTHROPIC_API_KEY", "DASHSCOPE_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setattr("harness.keychain.keychain_get", lambda name: None)
    r = route_role(FLAGSHIP)
    with pytest.raises(RoutingExhausted) as e:
        r.generate("x", seed=0, temperature=0.0, max_new_tokens=8)
    assert all(a.outcome == "auth_absent" for a in e.value.attempts)
    assert all(a.auth_source == "absent" for a in e.value.attempts)


def test_unknown_provider_and_role_fail_closed():
    with pytest.raises(ValueError):
        candidate("clippy")
    with pytest.raises(ValueError):
        chain_for_role("telepathy")


# --- end to end: a routing proposer feeds the accept path -------------------

def test_routing_proposer_drives_the_loop(tmp_path):
    from harness.loop import run_loop
    from harness.oracle import PytestOracle
    from harness.task import load_task
    task = load_task("tasks/example_pass", workdir=tmp_path / "wd")
    r = RoutingProposer([_c("p1")], builder=lambda c: _canned())
    res = run_loop(task, r, PytestOracle(), envelopes_dir=tmp_path / "env")
    assert res.accepted
    assert res.envelope.model_ref == "p1:m"
