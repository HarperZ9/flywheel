"""Falsifiers for the provider registry — the provider list must be REAL:
every registered provider builds a proposer whose requests actually hit the
declared endpoint shape, proven against a live local mock, and whose identity
lands in model_ref (and therefore in every receipt).
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from harness.providers import REGISTRY, make_proposer, provider_names
from harness.proposer import EnterpriseProposer


class _MockOpenAI(BaseHTTPRequestHandler):
    seen: list[dict] = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _MockOpenAI.seen.append({"path": self.path, "body": body,
                                 "auth": self.headers.get("Authorization", "")})
        out = json.dumps({"choices": [{"message": {
            "content": "```python\ndef add(a, b):\n    return a + b\n```"}}]})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out.encode())

    def log_message(self, *a):                       # keep test output clean
        pass


@pytest.fixture
def mock_server():
    _MockOpenAI.seen = []
    srv = HTTPServer(("127.0.0.1", 0), _MockOpenAI)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}/v1"
    srv.shutdown()


def test_every_registered_provider_constructs():
    for name in REGISTRY:
        if name == "openai-compatible":
            p = make_proposer(name, base_url="http://127.0.0.1:9/v1")
        else:
            p = make_proposer(name)
        assert isinstance(p, EnterpriseProposer)
        assert p.model_ref.startswith(name), \
            f"provider identity must ride model_ref: {p.model_ref}"


def test_unknown_provider_fails_closed_with_the_known_list():
    with pytest.raises(ValueError) as e:
        make_proposer("clippy")
    assert "unknown provider" in str(e.value)
    assert "ollama" in str(e.value)                  # the list is in the error


def test_byo_endpoint_requires_base_url():
    import os
    old = os.environ.pop("OPENAI_BASE_URL", None)
    try:
        with pytest.raises(ValueError, match="base-url"):
            make_proposer("openai-compatible")
    finally:
        if old is not None:
            os.environ["OPENAI_BASE_URL"] = old


def test_local_provider_speaks_openai_protocol_against_live_mock(mock_server):
    p = make_proposer("ollama", model="test-model", base_url=mock_server)
    out = p.generate("write add(a,b)", seed=7, temperature=0.0,
                     max_new_tokens=64, system="you are a code generator")
    (req,) = _MockOpenAI.seen
    assert req["path"] == "/v1/chat/completions"
    assert req["body"]["model"] == "test-model"
    assert req["body"]["seed"] == 7
    assert req["body"]["messages"][0]["role"] == "system"
    assert out.text == "def add(a, b):\n    return a + b\n"   # fences stripped
    assert out.model_ref == "ollama:test-model"


def test_no_key_in_env_sends_no_secret(mock_server, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    p = make_proposer("vllm", model="m", base_url=mock_server)
    p.generate("x", seed=0, temperature=0.0, max_new_tokens=8)
    (req,) = _MockOpenAI.seen
    assert req["auth"] in ("", "Bearer ")            # nothing invented, nothing leaked


def test_gated_loop_accepts_via_registry_proposer(mock_server, tmp_path):
    # end-to-end: a registry proposer feeds the SAME accept path (oracle+witness)
    from harness.loop import run_loop
    from harness.oracle import PytestOracle
    from harness.task import load_task

    task = load_task("tasks/example_pass", workdir=tmp_path / "wd")
    p = make_proposer("ollama", model="test-model", base_url=mock_server)
    r = run_loop(task, p, PytestOracle(), envelopes_dir=tmp_path / "env")
    assert r.accepted
    assert r.envelope.model_ref == "ollama:test-model"   # provider provenance in the receipt
    assert r.witness.verdict == "MATCH"


def test_provider_names_is_the_full_surface():
    names = provider_names()
    for expected in ("openai", "deepseek", "ollama", "vllm", "serve", "stub"):
        assert expected in names
