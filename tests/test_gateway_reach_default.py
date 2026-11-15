"""The reach rule is on in the gateway a user starts, and each transport keeps it alone.

The fifth independent review of 2.0.0 (findings T1 and T6) removed five lines,
one at a time, and no test failed:

  - `gateway.main` turning the rule on. Every test that needed the rule turned
    it on itself, so nothing held the shipped entry point to it.
  - the check in `CliBackend.chat` and the check in `proposer._send`, which
    had no test of their own.
  - the check in `endpoints_http.send` and the check in `endpoints_http._guard`.
    The one refusal test went through both, so either could go.

The first test starts `harness.gateway.main` in a new process with no fixture
(tests/gateway_reach_default_child.py) and asks for a model request outside an
account through every transport. The others mark this process as a gateway and
call one transport each, so that each check is the only one between the caller
and the stub. Each has a control with the rule off: the same call is sent,
which shows the refusal came from the rule and from nothing else.

A loopback stub stands in for the provider. No provider is called.
"""
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

from harness import endpoints_http, gateway_reach, proposer
from harness.endpoints import CliBackend
from tests import gateway_reach_default_child as child

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release
TRANSPORTS = ("endpoints_http.send", "proposer._send", "OpenAICompatBackend.chat",
              "EnterpriseProposer.generate", "CliBackend.chat")


def test_the_gateway_a_user_starts_refuses_a_model_request_outside_an_account(tmp_path):
    """T1. `gateway.main` in a fresh process: the rule is off before it and on while it
    serves, every transport refuses, and neither the stub nor a command line is reached."""
    done = subprocess.run(
        [sys.executable, "-m", "tests.gateway_reach_default_child",
         str(tmp_path / "home"), str(tmp_path)],
        capture_output=True, text=True, timeout=300,
        cwd=str(Path(__file__).resolve().parents[1]))
    assert done.returncode == 0, done.stdout + done.stderr
    seen = json.loads(done.stdout.strip().splitlines()[-1])
    assert seen["serving"] is True, done.stdout + done.stderr
    assert seen["before"] is False      # importing the gateway does not turn the rule on
    assert seen["enforced"] is True, "gateway.main served with the reach rule off"
    assert seen["outcomes"] == dict.fromkeys(TRANSPORTS, "Unaccounted")
    assert seen["arrivals"] == [] and seen["commands"] == 0


@pytest.fixture
def stub():
    server, arrivals = child.counting_stub()
    try:
        yield child.url_of(server), arrivals
    finally:
        server.shutdown()
        server.server_close()


def as_gateway():
    """Mark this process as a gateway with no ledger; conftest releases it after the test."""
    gateway_reach.enforce(lambda: None)


def post(url: str):
    return urllib.request.Request(f"{url}/v1/chat/completions", data=b"{}", method="POST",
                                  headers={"Content-Type": "application/json"})


def test_send_alone_refuses_outside_an_account(stub):
    url, arrivals = stub
    as_gateway()
    with pytest.raises(gateway_reach.Unaccounted):
        endpoints_http.send(post(url), 10)
    assert arrivals == []


def test_an_injected_transport_alone_is_refused_outside_an_account():
    """`_guard` is handed a transport that never reaches `send`, so its check is the only one."""
    calls = []
    as_gateway()
    with pytest.raises(gateway_reach.Unaccounted):
        endpoints_http._guard(lambda *args: calls.append(args) or (200, {}), "POST",
                              "http://127.0.0.1:9/v1/chat/completions", {}, b"{}", 10, "openai")
    assert calls == []


def test_a_command_line_backend_is_refused_outside_an_account():
    """T6. `CliBackend.chat` (the Claude and Codex command-line endpoints) starts no command."""
    commands = []
    backend = CliBackend(name="claude", argv=["claude", "-p", "{prompt}"],
                         runner=lambda cmd: commands.append(cmd) or (0, b"ok", b""))
    as_gateway()
    with pytest.raises(gateway_reach.Unaccounted):
        backend.chat([{"role": "user", "content": "hi"}], system="", max_tokens=8,
                     temperature=0, seed=0)
    assert commands == []


def test_the_hosted_proposers_send_is_refused_outside_an_account(stub):
    """T6. `proposer._send`, the one opener of the hosted proposers."""
    url, arrivals = stub
    as_gateway()
    with pytest.raises(gateway_reach.Unaccounted):
        proposer._send(post(url), 10)
    assert arrivals == []


@pytest.mark.parametrize("build", [
    lambda url: proposer.EnterpriseProposer(base_url=f"{url}/v1", model="stub-model",
                                            api_key="test-key"),
    lambda url: proposer.AnthropicProposer(base_url=url, model="stub-model",
                                           api_key="test-key"),
], ids=["enterprise", "anthropic"])
def test_a_hosted_proposer_is_refused_outside_an_account(stub, build):
    """T6. The proposers behind `/api/route` and the other endpoint-naming routes."""
    url, arrivals = stub
    as_gateway()
    with pytest.raises(gateway_reach.Unaccounted):
        build(url).generate("hi", seed=0, temperature=0, max_new_tokens=8)
    assert arrivals == []


def test_control_outside_a_gateway_process_each_transport_sends(stub):
    """The same calls with the rule off: each one reaches the stub or the runner."""
    url, arrivals = stub
    commands = []
    assert not gateway_reach.enforced()
    sends = child.transports(url, commands)
    assert set(sends) == set(TRANSPORTS)
    assert {name: child.attempt(send) for name, send in sends.items()} == \
        dict.fromkeys(TRANSPORTS, "sent")
    assert len(arrivals) == 4 and len(commands) == 1
    calls = []
    assert endpoints_http._guard(lambda *args: calls.append(args) or (200, {}), "POST",
                                 f"{url}/v1/chat/completions", {}, b"{}", 10,
                                 "openai") == (200, {})
    assert len(calls) == 1
