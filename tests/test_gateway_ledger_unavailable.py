"""With no ledger to record a call in, the gateway sends nothing upstream.

The gateway's ledger is unavailable when a second gateway runs on the same
Flywheel home, when another process holds the writer lock, and when the
ledger folder cannot be created or written. Before this was fixed a streamed
reply was delivered in full with no entry and no charge, a plain call reached
the provider and was then answered 500, and the chat path was served with no
entry at all.

Each test puts a real gateway on a loopback port in front of a stub upstream,
makes the ledger unavailable for one of the three causes, and asserts the
answer is 503 and the stub saw zero requests. No provider is called.
"""
import subprocess
import sys
import types

import pytest

from harness import gateway, gateway_ledger, gateway_ledger_gate
from tests import gateway_messages_support as support
from tests.gateway_keys_support import (  # noqa: F401  (fixtures)
    BODIES, MESSAGES, keyed, post, served, stream_bytes, turn2)

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release

CAUSES = ["second_gateway", "other_process", "unwritable_folder"]
CALLS = [("/v1/messages", False), ("/v1/messages", True), ("/v1/responses", False),
         ("/v1/responses", True), ("/v1/messages/count_tokens", False)]
_HOLD = ("import sys\nfrom harness import gateway_ledger\n"
         "held = gateway_ledger.GatewayLedger(sys.argv[1])\n"
         "print('held', flush=True)\nsys.stdin.read()\n")


@pytest.fixture
def home(monkeypatch, tmp_path):
    """A Flywheel home whose on-disk ledger the gateway under test opens."""
    where = tmp_path / "home"
    where.mkdir()
    monkeypatch.setenv("FLYWHEEL_HOME", str(where))
    yield where
    gateway_ledger.close_all()


@pytest.fixture
def unavailable(home):
    """make(cause) puts the home's ledger out of reach; it returns what frees it."""
    undo = []

    def make(cause: str):
        gateway_ledger.close_all()
        if cause == "second_gateway":       # the first gateway of this home, still running
            free = gateway_ledger.GatewayLedger(home).close
        elif cause == "other_process":      # any process that holds writer.lock
            child = subprocess.Popen([sys.executable, "-c", _HOLD, str(home)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            assert child.stdout.readline().strip() == "held"

            def free():
                if child.poll() is None:
                    child.stdin.close()
                    child.wait(20)
        else:                               # the folder cannot be created: a file is there
            blocker = home / gateway_ledger.DIR
            blocker.write_text("not a folder", encoding="utf-8")

            def free():
                if blocker.is_file():
                    blocker.unlink()
        undo.append(free)
        return free
    yield make
    for free in undo:
        free()


def _on_disk(monkeypatch, served, answers, provider="openai"):
    url, upstream, _memory = served(answers, provider)
    monkeypatch.setattr(gateway, "_ROUTER_LEDGER", None)    # use the home's ledger
    return url, upstream


def _request(path: str, stream: bool) -> dict:
    return {**BODIES.get(path, MESSAGES), "stream": stream} if stream else None


@pytest.mark.parametrize("path, stream", CALLS)
@pytest.mark.parametrize("cause", CAUSES)
def test_a_model_call_is_refused_503_before_any_upstream_call(
        keyed, served, monkeypatch, home, unavailable, cause, path, stream):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    answer = (support.stream_answer(stream_bytes("openai", "turn2")) if stream else turn2(1)[0])
    url, upstream = _on_disk(monkeypatch, served, [answer])
    unavailable(cause)
    for credential in (raw, support.TOKEN):         # a virtual key and the gateway token
        status, headers, body = post(url, path, credential, _request(path, stream))
        assert status == 503, body
        assert "ledger" in body["error"]["message"]
        assert "retry-after" in {name.lower() for name in headers}
    assert upstream.requests == [], "nothing reached the provider"
    assert keys.row("ci-bot")["totals"]["tokens"] == 0


@pytest.mark.parametrize("cause", CAUSES)
def test_control_the_same_gateway_serves_and_records_once_the_ledger_is_free(
        keyed, served, monkeypatch, home, unavailable, cause):
    keys, _store = keyed
    raw, _ = keys.create("ci-bot")
    url, upstream = _on_disk(monkeypatch, served, turn2(1))
    free = unavailable(cause)
    assert post(url, "/v1/messages", raw)[0] == 503 and upstream.requests == []
    free()
    assert post(url, "/v1/messages", raw)[0] == 200 and len(upstream.requests) == 1
    gateway_ledger.close_all()
    found, = gateway_ledger.check(home)
    assert found["ok"] and support.kinds(found["rows"]) == ["endpoint_call"]
    assert keys.row("ci-bot")["totals"]["tokens"] == 460


@pytest.mark.parametrize("cause", CAUSES)
def test_the_gateway_says_at_start_that_the_ledger_is_unavailable(home, unavailable, cause):
    unavailable(cause)
    lines = []
    assert gateway_ledger_gate.startup(gateway._router_ledger, out=lines.append) is False
    assert "UNAVAILABLE" in lines[0] and "503" in lines[0]


def test_control_the_start_line_names_the_ledger_file_when_it_opens(home):
    lines = []
    assert gateway_ledger_gate.startup(gateway._router_ledger, out=lines.append) is True
    assert "segment-000001.jsonl" in lines[0] and "UNAVAILABLE" not in lines[0]


class _Factory:
    """Stands in for the proposer factory of the chat paths; counts what it builds."""

    def __init__(self):
        self.ledgers, self.generated = [], 0

    def make(self, name, **kwargs):
        self.ledgers.append(kwargs.get("ledger"))
        return types.SimpleNamespace(generate=self._generate)

    def _generate(self, prompt, **kwargs):
        self.generated += 1
        return types.SimpleNamespace(text="ok", seed=0, prompt_hash="0" * 64,
                                     model_ref="openai:stub", usage=None, served_model="")


@pytest.fixture
def chat(monkeypatch):
    """The chat paths with a roster of one endpoint and a counting factory."""
    from harness import endpoint_registry
    factory = _Factory()
    monkeypatch.setattr(endpoint_registry, "make_endpoint_proposer", factory.make)
    monkeypatch.setattr(gateway, "_unified_roster", lambda: {
        "endpoints": [{"name": "openai", "credential": "present"}], "usable_names": ["openai"]})
    monkeypatch.setattr(gateway, "_ROUTER_LEDGER", None)
    return factory


_CHAT = {"model": "openai", "messages": [{"role": "user", "content": "What changed?"}]}


@pytest.mark.parametrize("cause", CAUSES)
def test_the_chat_paths_are_refused_503_and_build_no_proposer(home, unavailable, chat, cause):
    """The chat path once got a proposer with no ledger and served the call unrecorded."""
    unavailable(cause)
    body, status, receipt, _text, _ref = gateway.openai_chat(dict(_CHAT), "http://127.0.0.1:9")
    assert status == 503 and receipt is None
    assert body["error"]["code"] == "ledger_unavailable"
    routed, code = gateway.route_request("What changed?", "openai")
    assert code == 503 and routed["error"]["code"] == "ledger_unavailable"
    assert chat.ledgers == [] and chat.generated == 0, "no proposer was built or called"


def test_control_the_chat_paths_get_the_ledger_when_it_opens(home, chat):
    _body, status, _receipt, _text, _ref = gateway.openai_chat(dict(_CHAT), "http://127.0.0.1:9")
    assert status == 200 and chat.generated == 1
    assert isinstance(chat.ledgers[0], gateway_ledger.GatewayLedger)
