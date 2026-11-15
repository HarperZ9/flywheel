"""The chat routes record a failed provider call, through the one accounting object.

Fifth review round of 2.0.0, the lead's ruling 2. On /v1/chat/completions and
/api/route a provider error left no ledger entry, although the provider had
been contacted (probed in round 4: two upstream calls, no entries). These two
routes record through `LedgeredProposer`, which now uses the same accounting
object as the model interfaces (`gateway_account.Call`): a started entry
before the provider is contacted, and one end entry whatever happens.

The routes are called as functions here (`gateway.openai_chat`,
`gateway.route_request`), the layer the HTTP handler calls after its grant
step; the HTTP path of these two routes is not driven by these tests. A stub
upstream on a loopback port. No provider is called.
"""
from dataclasses import replace

import pytest

from harness import gateway, gateway_ledger, providers
from harness.endpoint_ledgered import LedgeredProposer
from harness.local_session import SessionLedger
from harness.proposer import ProposerOutput
from tests import gateway_messages_support as support
from tests.gateway_keys_support import turn2

pytestmark = pytest.mark.release_gate   # run against the built wheel before a release

STARTED = "endpoint_call_started"
BOOM = support.json_answer({"error": {"message": "boom", "type": "server_error"}}, 500)
CHAT = {"model": "ollama:stub-model", "messages": [{"role": "user", "content": "Hi."}]}


@pytest.fixture
def chat_route(monkeypatch):
    """start(replies) -> (upstream, ledger): `ollama` pointed at a loopback stub."""
    opened = []

    def start(replies, ledger=None):
        ledger = SessionLedger() if ledger is None else ledger
        monkeypatch.setattr(gateway, "_ROUTER_LEDGER", ledger)
        monkeypatch.setattr(gateway, "_unified_roster", lambda: {
            "endpoints": [{"name": "ollama", "credential": "local-none"}],
            "usable_names": ["ollama"]})
        upstream = support.Upstream(replies).__enter__()
        opened.append(upstream)
        monkeypatch.setitem(providers.REGISTRY, "ollama", replace(
            providers.REGISTRY["ollama"], base_url=f"{upstream.url}/v1"))
        return upstream, ledger
    yield start
    for upstream in opened:
        upstream.__exit__(None, None, None)


def test_a_provider_error_on_either_chat_route_leaves_a_failed_entry(chat_route):
    upstream, ledger = chat_route([BOOM, BOOM])
    _body, code, *_rest = gateway.openai_chat(CHAT, "http://127.0.0.1:9")
    _answer, status = gateway.route_request("Hi.", "ollama", "stub-model")
    assert (code, status) == (502, 502) and len(upstream.requests) == 2
    entries = support.recorded(ledger)              # each has its started entry before it
    assert len(entries) == len(upstream.requests), (
        f"{len(upstream.requests)} upstream call(s) and {len(entries)} ledger entries")
    for entry in entries:
        assert (entry.kind, entry.content) == ("endpoint_call_failed", "upstream_error")
        assert entry.meta["endpoint"] == "ollama" and len(entry.meta["prompt_sha"]) == 16
        assert entry.meta["reason"] == "upstream_error" and entry.meta["error"]
    assert ledger.verify()


def test_control_a_served_chat_call_leaves_a_start_and_a_served_entry(chat_route):
    upstream, ledger = chat_route(turn2(1))
    _body, code, *_rest = gateway.openai_chat(CHAT, "http://127.0.0.1:9")
    assert code == 200 and len(upstream.requests) == 1
    assert [entry.kind for entry in ledger.entries] == [STARTED, "endpoint_call"]


def test_a_chat_call_whose_start_cannot_be_written_is_not_sent(chat_route):
    class Full(SessionLedger):
        def append(self, kind, content, meta=None):
            raise OSError(28, "No space left on device")
    upstream, ledger = chat_route(turn2(2), Full())
    body, code, *_rest = gateway.openai_chat(CHAT, "http://127.0.0.1:9")
    assert code == 502 and "all providers failed" in body["error"]["message"]
    answer, status = gateway.route_request("Hi.", "ollama", "stub-model")
    assert status == 502 and "nothing was sent upstream" in answer["error"]
    assert upstream.requests == [], "a call with no started entry reached the provider"


class _Inner:
    """A proposer that notes what the ledger's segment held when it was called."""
    model_ref = "prov:m1"

    def __init__(self, home, fail=False):
        self.home, self.fail, self.seen = home, fail, []

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        self.seen.append([entry.kind for segment in gateway_ledger.check(self.home)
                          for entry in segment["rows"]])
        if self.fail:
            raise ConnectionError("planted by the test")
        return ProposerOutput("an answer", self.model_ref, seed, "ph", "miss")


@pytest.mark.parametrize("fail", [False, True])
def test_the_started_entry_is_on_disk_before_the_proposer_runs(tmp_path, fail):
    ledger = gateway_ledger.GatewayLedger(tmp_path / "home")
    try:
        inner = _Inner(tmp_path / "home", fail)
        proposer = LedgeredProposer(inner, ledger, endpoint="prov")
        if fail:
            with pytest.raises(ConnectionError):
                proposer.generate("a prompt", seed=0, temperature=0.0, max_new_tokens=8)
        else:
            proposer.generate("a prompt", seed=0, temperature=0.0, max_new_tokens=8)
        assert inner.seen == [[STARTED]], "the proposer ran before its started entry was on disk"
        start, end = ledger.entries
        assert end.kind == ("endpoint_call_failed" if fail else "endpoint_call")
        assert end.meta["call"] == start.content and end.meta["endpoint"] == "prov"
        assert ledger.calls.open == {}              # the call has its end: nothing unsettled
    finally:
        ledger.close()


def test_the_proposer_class_is_still_reachable_from_the_registry():
    """It moved to its own module; the pinned registry loads it on first use."""
    from harness import endpoint_registry
    assert endpoint_registry.LedgeredProposer is LedgeredProposer
    made = endpoint_registry.make_endpoint_proposer("stub", ledger=SessionLedger())
    assert isinstance(made, LedgeredProposer)
    assert not isinstance(endpoint_registry.make_endpoint_proposer("stub"), LedgeredProposer)


# --- /v1/embeddings: a hosted provider call that was outside the ledger --------------------

class _Answer:
    def __init__(self, body: bytes, status: int = 200):
        self.body, self.status = body, status

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def embeddings(monkeypatch):
    """start(answer) -> (requests, ledger): provider `xprov` behind a fake `urlopen`.
    `answer` is an `_Answer`, or an exception to raise."""
    def start(answer, ledger=None):
        spec = type("Spec", (), {"base_url": "https://api.x.example/v1", "api_key_env": "X_KEY",
                                 "local": False, "default_model": "e"})()
        monkeypatch.setitem(providers.REGISTRY, "xprov", spec)
        monkeypatch.setenv("X_KEY", "not-a-real-key")
        ledger = SessionLedger() if ledger is None else ledger
        monkeypatch.setattr(gateway, "_ROUTER_LEDGER", ledger)
        requests = []

        def urlopen(request, timeout=60):
            requests.append(request.full_url)
            if isinstance(answer, BaseException):
                raise answer
            return answer
        monkeypatch.setattr(gateway.urllib.request, "urlopen", urlopen)
        return requests, ledger
    return start


EMBED = {"model": "xprov:embed-3", "input": "hi"}


def test_an_embeddings_call_is_recorded_with_its_start_before_the_provider(embeddings):
    requests, ledger = embeddings(_Answer(
        b'{"data":[{"embedding":[0.1,0.2]}],"usage":{"prompt_tokens":2,"total_tokens":2}}'))
    body, code = gateway.openai_embeddings(EMBED)
    assert code == 200 and body["data"][0]["embedding"] == [0.1, 0.2] and len(requests) == 1
    entry, = support.recorded(ledger)
    assert [e.kind for e in ledger.entries] == [STARTED, "endpoint_call"]
    assert entry.meta["interface"] == "openai-embeddings" and entry.meta["key"] == "owner"
    assert entry.meta["model_ref"] == "xprov:embed-3" and entry.meta["input_tokens"] == 2
    assert entry.meta["usage_reported"] is True and entry.content == entry.meta["response_sha"]
    assert "not-a-real-key" not in ledger.to_jsonl() and "hi" not in [
        value for e in ledger.entries for value in e.meta.values()]


def test_a_failed_embeddings_call_leaves_a_failed_entry(embeddings):
    import io
    import urllib.error
    refused = urllib.error.HTTPError("https://api.x.example/v1/embeddings", 429, "Too Many",
                                     {}, io.BytesIO(b'{"error":{"message":"slow down"}}'))
    requests, ledger = embeddings(refused)
    body, code = gateway.openai_embeddings(EMBED)
    assert code == 429 and body["error"]["message"] == "slow down" and len(requests) == 1
    entry, = support.recorded(ledger)
    assert (entry.kind, entry.content) == ("endpoint_call_failed", "upstream_status_429")
    requests, ledger = embeddings(ConnectionResetError("planted by the test"))
    body, code = gateway.openai_embeddings(EMBED)
    assert code == 502 and len(requests) == 1
    entry, = support.recorded(ledger)
    assert (entry.kind, entry.content, entry.meta["error"]) == (
        "endpoint_call_failed", "upstream_error", "ConnectionResetError")


def test_an_embeddings_call_with_no_ledger_or_no_start_is_not_sent(embeddings, monkeypatch):
    class Full(SessionLedger):
        def append(self, kind, content, meta=None):
            raise OSError(28, "No space left on device")
    requests, _ledger = embeddings(_Answer(b'{"data":[]}'), Full())
    body, code = gateway.openai_embeddings(EMBED)
    assert code == 503 and "nothing was sent upstream" in body["error"]["message"]
    monkeypatch.setattr(gateway, "_router_ledger", lambda: None)    # the ledger cannot be opened
    body, code = gateway.openai_embeddings(EMBED)
    assert code == 503 and body["error"]["code"] == "ledger_unavailable"
    assert requests == [], "an embeddings call with no record reached the provider"


def test_control_an_embeddings_request_refused_before_contact_leaves_no_entry(embeddings):
    requests, ledger = embeddings(_Answer(b'{"data":[]}'))
    assert gateway.openai_embeddings({"model": "no-such", "input": "hi"})[1] == 400
    assert requests == [] and ledger.entries == []
