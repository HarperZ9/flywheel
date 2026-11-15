"""Falsifiers for the standalone local agent (the offline / exhaustion tier).

Load-bearing behaviors, each asserted with an injected transport (no network,
no GPU):
  (1) the router picks the trained-model backend when it is live, and FAILS OVER
      to Ollama when serve is down OR errors mid-turn;
  (2) when NO local backend is healthy, send() raises loudly (never a silent
      empty answer) — the exact 'keep working offline' failure must be visible;
  (3) every served turn carries a receipt whose id changes with the response,
      and multi-turn history is preserved;
  (4) a malformed backend response is a typed BackendError, not a crash;
  (5) the strongest local model (32b > 14b > 7b) is preferred automatically, so
      pulling the 14B/32B upgrades the backend with no code change.
"""
import urllib.error

import pytest

from relay.local_agent import (
    BackendError,
    LocalAgent,
    OllamaBackend,
    ServeBackend,
    _prefer_largest,
    health_report,
    select_backend,
)


class FakeTransport:
    """Routes (method, url, body) by URL substring to a scripted response or
    exception. Records calls so failover order is checkable."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, method, url, body, timeout):
        self.calls.append(url)
        for key, resp in self.routes.items():
            if key in url:
                if isinstance(resp, Exception):
                    raise resp
                if callable(resp):
                    return resp(method, body)
                return resp
        raise urllib.error.URLError(f"no route: {url}")


SERVE_LIVE = {"/health": (200, {"ok": True, "model_ref": "14b"}),
              "/generate": (200, {"text": "from serve", "model_ref": "14b",
                                   "prompt_hash": "aa", "seed": 0})}
OLLAMA_LIVE = {"/api/tags": (200, {"models": [{"name": "qwen2.5:7b"}]}),
               "/api/chat": (200, {"message": {"content": "from ollama"}})}


def _agent(routes, prefer="auto"):
    t = FakeTransport(routes)
    backends = [ServeBackend(transport=t), OllamaBackend(transport=t)]
    return LocalAgent(backends=backends, prefer=prefer), t


def test_prefers_trained_model_when_serve_is_live():
    agent, _ = _agent({**SERVE_LIVE, **OLLAMA_LIVE})
    resp = agent.send("hello")
    assert resp["content"][0]["text"] == "from serve"
    assert resp["backend"] == "serve"
    assert resp["x_receipt"]["model_ref"] == "14b"


def test_fails_over_to_ollama_when_serve_is_down():
    # serve /health raises (down); ollama live -> the offline tier still answers
    routes = {"/health": urllib.error.URLError("serve down"),
              "/generate": urllib.error.URLError("serve down"), **OLLAMA_LIVE}
    agent, _ = _agent(routes)
    resp = agent.send("hi")
    assert resp["backend"] == "ollama"
    assert resp["content"][0]["text"] == "from ollama"


def test_fails_over_when_serve_is_healthy_but_generate_errors():
    # serve passes health but /generate returns 500 -> must fall over, not die
    routes = {"/health": (200, {"ok": True, "model_ref": "14b"}),
              "/generate": (500, {"error": "cuda oom"}), **OLLAMA_LIVE}
    agent, t = _agent(routes)
    resp = agent.send("hi")
    assert resp["backend"] == "ollama"
    assert any("/generate" in c for c in t.calls)   # serve WAS attempted first


def test_no_healthy_backend_raises_loud():
    routes = {"/health": urllib.error.URLError("down"),
              "/api/tags": urllib.error.URLError("down")}
    agent, _ = _agent(routes)
    with pytest.raises(BackendError, match="no local backend is healthy"):
        agent.send("anyone home?")


def test_receipt_changes_with_response_and_history_is_kept():
    # two different served answers -> two different receipt ids; history grows
    answers = iter([(200, {"text": "answer one", "model_ref": "14b", "seed": 0}),
                    (200, {"text": "answer two", "model_ref": "14b", "seed": 0})])
    routes = {"/health": (200, {"ok": True, "model_ref": "14b"}),
              "/generate": lambda m, b: next(answers)}
    agent, _ = _agent(routes)
    r1 = agent.send("q1")
    r2 = agent.send("q2")
    assert r1["x_receipt"]["receipt_id"] != r2["x_receipt"]["receipt_id"]
    # user+assistant recorded for both turns
    assert [h["role"] for h in agent.history] == ["user", "assistant", "user", "assistant"]
    assert agent.history[1]["content"] == "answer one"


def test_malformed_ollama_response_is_typed_error_not_crash():
    routes = {"/health": urllib.error.URLError("no serve"),
              "/api/tags": (200, {"models": [{"name": "qwen2.5:7b"}]}),
              "/api/chat": (200, {"unexpected": "shape"})}   # no message.content
    agent, _ = _agent(routes)
    with pytest.raises(BackendError):
        agent.send("hi")


def test_select_backend_respects_forced_choice():
    t = FakeTransport({**SERVE_LIVE, **OLLAMA_LIVE})
    backends = [ServeBackend(transport=t), OllamaBackend(transport=t)]
    assert select_backend(backends, prefer="ollama").name == "ollama"
    assert select_backend(backends, prefer="auto").name == "serve"


def test_prefer_largest_picks_the_strongest_local_model():
    assert _prefer_largest(["qwen2.5:7b", "qwen2.5:0.5b"]) == "qwen2.5:7b"
    assert _prefer_largest(["a:7b", "b:32b", "c:14b"]) == "b:32b"


def test_health_report_shape():
    t = FakeTransport({**SERVE_LIVE, **OLLAMA_LIVE})
    rep = health_report([ServeBackend(transport=t), OllamaBackend(transport=t)])
    assert rep["any_live"] is True
    assert {tier["backend"] for tier in rep["tiers"]} == {"serve", "ollama"}


def _stream_pieces(pieces):
    def st(body):
        for p in pieces:
            yield {"message": {"content": p}}
        yield {"done": True}
    return st


def test_ollama_chat_stream_yields_content_chunks():
    b = OllamaBackend(stream_transport=_stream_pieces(["hel", "lo", " world"]))
    b._resolved = "qwen2.5:7b"
    chunks = list(b.chat_stream([{"role": "user", "content": "hi"}],
                                system="", max_tokens=10, temperature=0, seed=0))
    assert chunks == ["hel", "lo", " world"]


def test_agent_stream_accumulates_and_still_receipts():
    t = FakeTransport({"/api/tags": (200, {"models": [{"name": "qwen2.5:7b"}]})})
    b = OllamaBackend(transport=t, stream_transport=_stream_pieces(["ans", "wer"]))
    agent = LocalAgent(backends=[b])
    seen = []
    resp = agent.stream("hi", seen.append)
    assert "".join(seen) == "answer"
    assert resp["content"][0]["text"] == "answer" and resp["backend"] == "ollama"
    assert resp["x_receipt"]["receipt_id"]
    assert [h["role"] for h in agent.history] == ["user", "assistant"]


def test_stream_falls_back_when_no_streaming_backend():
    t = FakeTransport({**SERVE_LIVE})
    agent = LocalAgent(backends=[ServeBackend(transport=t)])   # serve has no chat_stream
    seen = []
    resp = agent.stream("hi", seen.append)
    assert resp["backend"] == "serve" and seen == ["from serve"]
    assert [h["role"] for h in agent.history] == ["user", "assistant"]   # no dup user turn


def test_stream_error_chunk_raises_not_silently_receipted():
    # Ollama emits tokens, then a mid-stream {"error": ...} and stops. The old code
    # dropped the error chunk and receipted the PARTIAL text as a finished turn.
    # It must instead name the failure loudly, never mint a receipt over a fragment.
    def st(body):
        yield {"message": {"content": "par"}}
        yield {"error": "cuda out of memory"}
    b = OllamaBackend(stream_transport=st)
    b._resolved = "qwen2.5:7b"
    with pytest.raises(BackendError, match="cuda out of memory"):
        list(b.chat_stream([{"role": "user", "content": "hi"}],
                           system="", max_tokens=10, temperature=0, seed=0))


def test_stream_without_done_terminator_is_a_named_truncation():
    # A stream that closes cleanly without the done:true terminator is truncated,
    # not a completed turn.
    def st(body):
        yield {"message": {"content": "partial"}}      # no done:true
    b = OllamaBackend(stream_transport=st)
    b._resolved = "qwen2.5:7b"
    with pytest.raises(BackendError, match="truncat"):
        list(b.chat_stream([{"role": "user", "content": "hi"}],
                           system="", max_tokens=10, temperature=0, seed=0))


def test_failover_errors_are_surfaced_on_eventual_success():
    # serve passes health but /generate 500s; ollama answers. The failed serve
    # attempt must appear on the response (not be discarded on success), so an
    # auditor can see the trained tier failed mid-run.
    routes = {"/health": (200, {"ok": True, "model_ref": "14b"}),
              "/generate": (500, {"error": "cuda oom"}), **OLLAMA_LIVE}
    agent, _ = _agent(routes)
    resp = agent.send("hi")
    assert resp["backend"] == "ollama"
    assert resp.get("failover") and any("serve" in e for e in resp["failover"])


def test_hosted_turn_records_seed_not_applied():
    # A hosted backend never transmits a seed, so the receipt must not claim one.
    from relay.endpoints import OpenAICompatBackend

    def tp(method, url, headers, body, timeout):
        return 200, {"choices": [{"message": {"content": "hi"}}]}
    b = OpenAICompatBackend(name="deepseek", base_url="http://x", model="m", transport=tp)
    agent = LocalAgent(backends=[b])
    resp = agent.send("q")
    assert resp["x_receipt"]["seed"] is None                 # non-reproducible, not seed 0


def test_serve_turn_still_records_the_applied_seed():
    agent, _ = _agent({**SERVE_LIVE, **OLLAMA_LIVE})
    resp = agent.send("hi")
    assert resp["x_receipt"]["seed"] == 0                    # serve pins the seed it was given
