"""A provider key is never re-sent to the host a redirect points at.

Sixth review round of 2.0.0, finding S6 of the fourth independent review
(probe r4probes/p6_redirect.py). On /v1/embeddings and /api/route a 302 from
the provider host was followed and the provider key arrived at the second
host, while docs/KNOWN-LIMITS-2.0.0.md said redirects are refused.

Stub A answers every request with a redirect to stub B, which records what it
receives. Each client that sends a credential is pointed at A. The assertion
is on B: it received nothing. The key is a test string and no provider is
called. The last test is the control: a plain `urlopen` does carry the key to
B, so the stubs can show the fault.
"""
import json
import threading
import types
import urllib.error
import urllib.request
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from harness import gateway, gateway_embeddings, providers

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release
KEY = "sk-test-not-a-real-key"


def _serve(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


@pytest.fixture(params=[301, 302, 303, 307, 308])
def hosts(request):
    """(url of A, what B received, how many requests A received)."""
    seen, first = [], []

    class B(BaseHTTPRequestHandler):
        def _any(self):
            if self.command == "POST":
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
            seen.append((self.command, self.path, self.headers.get("Authorization"),
                         self.headers.get("x-api-key")))
            body = json.dumps({"data": [], "usage": {"prompt_tokens": 1}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        do_GET = do_POST = _any

        def log_message(self, *args):
            pass
    b_server, b_url = _serve(B)

    class A(BaseHTTPRequestHandler):
        def _any(self):
            if self.command == "POST":
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
            first.append(self.path)
            self.send_response(request.param)
            self.send_header("Location", b_url + "/elsewhere")
            self.send_header("Content-Length", "0")
            self.end_headers()
        do_GET = do_POST = _any

        def log_message(self, *args):
            pass
    a_server, a_url = _serve(A)
    yield a_url, seen, first
    for server in (a_server, b_server):
        server.shutdown()
        server.server_close()


@pytest.fixture
def ledger(monkeypatch):
    from harness.local_session import SessionLedger
    made = SessionLedger()
    monkeypatch.setattr(gateway, "_ROUTER_LEDGER", made)
    return made


def test_embeddings_do_not_follow_a_redirect(hosts, ledger):
    a_url, seen, first = hosts
    spec = types.SimpleNamespace(local=False, api_key_env="FAKE_KEY", base_url=a_url + "/v1",
                                 default_model="m")
    _body, status = gateway_embeddings.openai_embeddings(
        {"model": "openai:text-embedding-3-small", "input": "hi"},
        providers_registry={"openai": spec}, urllib_module=urllib,
        resolve_credential=lambda name: KEY, ledger_of=gateway._router_ledger)
    assert len(first) == 1 and seen == []
    assert 300 <= status < 400          # the redirect is the answer
    assert [entry.kind for entry in ledger.entries] == ["endpoint_call_started",
                                                        "endpoint_call_failed"]


def test_api_route_does_not_follow_a_redirect(hosts, ledger, monkeypatch):
    a_url, seen, first = hosts
    monkeypatch.setenv("FAKE_KEY", KEY)
    name = next(n for n, s in providers.REGISTRY.items()
                if getattr(s, "api_key_env", None) and not getattr(s, "local", False)
                and n not in ("anthropic", "gemini"))
    monkeypatch.setitem(providers.REGISTRY, name, replace(
        providers.REGISTRY[name], base_url=a_url + "/v1", api_key_env="FAKE_KEY"))
    monkeypatch.setattr(gateway, "_unified_roster", lambda: {
        "endpoints": [{"name": name, "credential": "present"}], "usable_names": [name]})
    _body, status = gateway.route_request("Hi.", name, "m")
    assert status == 502 and len(first) == 1 and seen == []
    assert [entry.kind for entry in ledger.entries] == ["endpoint_call_started",
                                                        "endpoint_call_failed"]


def test_the_anthropic_proposer_does_not_follow_a_redirect(hosts):
    a_url, seen, first = hosts
    from harness.proposer import AnthropicProposer
    with pytest.raises(Exception):
        AnthropicProposer(base_url=a_url, api_key=KEY).generate(
            "hi", seed=0, temperature=0.0, max_new_tokens=8)
    assert len(first) == 1 and seen == []


@pytest.mark.parametrize("kind", ["openai", "anthropic", "gemini"])
def test_the_backends_do_not_follow_a_redirect(hosts, kind):
    a_url, seen, first = hosts
    from harness.endpoints import AnthropicBackend, GeminiBackend, OpenAICompatBackend
    backend = {"openai": lambda: OpenAICompatBackend(name="openai", base_url=a_url + "/v1",
                                                     model="m", api_key=KEY),
               "anthropic": lambda: AnthropicBackend(name="anthropic", base_url=a_url,
                                                     model="m", api_key=KEY),
               "gemini": lambda: GeminiBackend(name="gemini", base_url=a_url + "/v1beta",
                                               model="m", api_key=KEY)}[kind]()
    with pytest.raises(Exception):
        backend.chat([{"role": "user", "content": "hi"}], system="", max_tokens=8,
                     temperature=0, seed=0)
    assert first and seen == []


def test_the_model_list_read_does_not_follow_a_redirect(hosts):
    a_url, seen, first = hosts
    from harness import model_roster
    with pytest.raises(urllib.error.HTTPError):
        model_roster._fetch_ids(a_url + "/v1", KEY, 10)
    assert len(first) == 1 and seen == []


def test_the_preaction_judge_does_not_follow_a_redirect(hosts, monkeypatch):
    a_url, seen, first = hosts
    from harness.preaction.judge import HttpJudge, JudgeConfig
    monkeypatch.setenv("FAKE_KEY", KEY)
    judge = HttpJudge(JudgeConfig(endpoint=a_url + "/v1", model="m", api_key_env="FAKE_KEY"))
    with pytest.raises(urllib.error.HTTPError):
        judge._post(b"{}")
    assert len(first) == 1 and seen == []


def test_the_arc_client_does_not_follow_a_redirect(hosts):
    a_url, seen, first = hosts
    from harness import arc_agi3
    with pytest.raises(urllib.error.HTTPError):
        arc_agi3._default_transport("GET", "/api/games", None, api_key=KEY, base_url=a_url)
    assert len(first) == 1 and seen == []


def test_control_a_plain_urlopen_carries_the_key_to_the_second_host(hosts):
    a_url, seen, _first = hosts
    request = urllib.request.Request(a_url + "/v1/models",
                                     headers={"Authorization": f"Bearer {KEY}"})
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()
    assert seen == [("GET", "/elsewhere", f"Bearer {KEY}", None)]
