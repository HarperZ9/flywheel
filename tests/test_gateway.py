"""gateway contract — the two SUPERAPP increment-2 falsifiers, unit-level.

Both verifiers must be able to fail:
  - a down local endpoint reads as unhealthy (not silently healthy)
  - touching a cataloged receipt moves the world root hash
Plus: enterprise providers expose credential-presence booleans, never values.
"""
import json

from harness import gateway


def test_world_root_hash_changes_when_a_receipt_changes(tmp_path):
    (tmp_path / "a.json").write_text('{"v": 1}', encoding="utf-8")
    catalog = ("a.json",)
    before = gateway.world_state(tmp_path, catalog)["root_hash"]
    (tmp_path / "a.json").write_text('{"v": 2}', encoding="utf-8")
    after = gateway.world_state(tmp_path, catalog)["root_hash"]
    assert before != after, "root hash did not move on a receipt change — catalog is fake"


def test_world_marks_missing_receipts_honestly(tmp_path):
    w = gateway.world_state(tmp_path, ("does_not_exist.json",))
    assert w["present_count"] == 0
    assert w["receipts"][0]["sha256"] == "MISSING"
    assert w["receipts"][0]["present"] is False


def test_world_root_hash_stable_when_nothing_changes(tmp_path):
    (tmp_path / "a.json").write_text("stable", encoding="utf-8")
    h1 = gateway.world_state(tmp_path, ("a.json",))["root_hash"]
    h2 = gateway.world_state(tmp_path, ("a.json",))["root_hash"]
    assert h1 == h2


def test_down_local_endpoint_reads_unhealthy():
    # ports chosen to be almost certainly closed -> probe must fail closed
    roster = gateway.endpoint_roster("http://127.0.0.1:9", "http://127.0.0.1:9")
    assert roster["local_healthy"] == 0
    assert all(e["healthy"] is False for e in roster["local"])


def test_enterprise_reports_credential_presence_not_values(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-canary-value")
    roster = gateway.endpoint_roster("http://127.0.0.1:9", "http://127.0.0.1:9")
    blob = json.dumps(roster)
    assert "sk-fake-canary-value" not in blob, "a key VALUE leaked into the roster"
    codex = next((e for e in roster["enterprise"] if e["name"] == "codex"), None)
    if codex is not None:  # roster present only if endpoints.py imported
        assert codex["credential_present"] is True
        assert codex["key_env"] == "OPENAI_API_KEY"


def test_spine_roster_present():
    w = gateway.world_state(gateway.REPO)
    assert "local-model" in w["spine"] and "telos" in w["spine"]


# --- companion route: the two SUPERAPP increment-5 falsifiers ------------------

from types import SimpleNamespace

from harness.companion import CompanionSeat
from harness.proposer import ProposerOutput


class _CyclingProposer:
    model_ref = "stub"

    def __init__(self, texts):
        self.texts = texts
        self.calls = 0

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        t = self.texts[self.calls % len(self.texts)]
        self.calls += 1
        return ProposerOutput(t, self.model_ref, seed, "h", "stub")


class _OneProposer:
    model_ref = "stub"

    def __init__(self, text):
        self.text = text
        self.calls = 0

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        self.calls += 1
        return ProposerOutput(self.text, self.model_ref, seed, "h", "stub")


class _FakeOracle:
    def __init__(self, marker):
        self.marker = marker

    def verify(self, candidate, task):
        return SimpleNamespace(passed=self.marker in candidate)


def test_companion_cache_hit_triggers_no_frontier_call():
    # Falsifier 1: a proof-cached fact must answer at ~0 cost, with NO escalate in
    # the ledger. Seat over an oracle-verified accept so the answer is cached, then
    # ask again -> the second answer is a cache hit, and no ledger row escalates.
    seat = CompanionSeat(_OneProposer("def f(a):\n    return a + 1\n"),
                         oracle=_FakeOracle("+ 1"),
                         cache=gateway._MemoryProofCache())
    sig = "def f(a):\n    return a + 1\n"
    first = gateway.companion_answer(seat, "add one", sig)
    assert first["source"] == "local-verified"
    second = gateway.companion_answer(seat, "add one", sig)
    assert second["source"] == "cache"
    assert second["text"] == "def f(a):\n    return a + 1\n"
    assert all(row["source"] != "escalate" for row in seat.ledger), \
        "a cached fact triggered an escalation -- increment-5 falsifier 1 broken"


def test_companion_escalate_carries_ledgered_failed_local_receipt():
    # Falsifier 2: on a local failure the escalate decision must be PRECEDED by a
    # ledgered failed-local SelectionReceipt -- escalation is a verdict on evidence,
    # never a bare guess. Distinct-disagreeing candidates + no oracle -> escalate.
    distinct = [f"def f(a):\n    return a + {i}\n" for i in range(64)]
    seat = CompanionSeat(_CyclingProposer(distinct), oracle=None,
                         cache=gateway._MemoryProofCache(), max_n=16)
    out = gateway.companion_answer(seat, "hard task", "def f(a):\n    return a + 1\n")
    assert out["source"] == "escalate"
    assert out["text"] is None                    # no accepted answer travels on escalate
    assert out["escalate_to"] == "anthropic"
    assert out["best_effort_text"] is not None    # the failed local attempt is preserved
    row = seat.ledger[-1]
    assert row["source"] == "escalate"
    assert row["receipt"]["verdict"] == "ESCALATE"
    assert row["receipt"]["candidates_used"] > 0, \
        "escalate has no evidence of a real local attempt -- increment-5 falsifier 2 broken"


def test_companion_answer_never_calls_frontier_inline():
    # The frontier tier is only NAMED, never invoked, from the seat/route: the
    # escalate_to endpoint is a string, and routing to it is a caller-gated action.
    seat = CompanionSeat(_CyclingProposer([f"x{i}" for i in range(64)]), oracle=None,
                         cache=gateway._MemoryProofCache(), max_n=8)
    out = gateway.companion_answer(seat, "anything")
    assert isinstance(out["escalate_to"], str) and out["text"] is None


# --- training status route (read-only) -----------------------------------------

def test_route_answer_mints_recheckable_receipt_with_provenance():
    # The universal router's differentiator: every routed call carries a receipt
    # that recomputes from its parts, and the provider provenance rides model_ref.
    out = gateway.route_answer("hi there", "some-provider", _OneProposer("routed reply"),
                               credential="present")
    assert out["schema"] == "flywheel.route-result/v1"
    assert out["endpoint"] == "some-provider"
    assert out["text"] == "routed reply"
    assert out["model_ref"] == "stub"
    from harness.messages_api import make_receipt
    expect = make_receipt(
        {"prompt": "hi there", "system": "", "max_new_tokens": 512, "temperature": 0.0, "seed": 0},
        {"text": "routed reply", "seed": 0, "prompt_hash": "h"}, "stub")
    assert out["receipt"]["receipt_id"] == expect["receipt_id"]   # third party re-derives it


def test_route_request_refuses_unknown_endpoint(monkeypatch):
    monkeypatch.setattr(gateway, "_unified_roster",
                        lambda: {"endpoints": [{"name": "real", "credential": "present"}],
                                 "usable_names": ["real"]})
    body, code = gateway.route_request("hi", "no-such-provider")
    assert code == 404 and "unknown endpoint" in body["error"]


def test_route_request_gates_on_credential_presence(monkeypatch):
    # A hosted endpoint with no key present is refused honestly, never silently
    # falling back to a local model (which would forge provenance).
    monkeypatch.setattr(gateway, "_unified_roster",
                        lambda: {"endpoints": [{"name": "openai", "credential": "absent"}],
                                 "usable_names": []})
    body, code = gateway.route_request("hi", "openai")
    assert code == 400 and body["credential"] == "absent"


def test_route_request_success_routes_and_receipts(monkeypatch):
    monkeypatch.setattr(gateway, "_unified_roster",
                        lambda: {"endpoints": [{"name": "local-x", "credential": "local-none"}],
                                 "usable_names": ["local-x"]})
    import harness.endpoint_registry as er
    monkeypatch.setattr(er, "make_endpoint_proposer",
                        lambda name, ledger=None: _OneProposer("routed answer"))
    body, code = gateway.route_request("hi", "local-x")
    assert code == 200
    assert body["schema"] == "flywheel.route-result/v1"
    assert body["text"] == "routed answer"
    assert body["receipt"]["receipt_id"]
    assert body["endpoint"] == "local-x"


# --- OpenAI-compatible surface -------------------------------------------------

def _fake_handler(cors):
    h = gateway._Handler.__new__(gateway._Handler)
    h.cors = cors
    return h


def test_cors_off_by_default():
    h = _fake_handler(False)
    hdrs = []
    h.send_header = lambda k, v: hdrs.append((k, v))
    h._cors()
    assert not any(k == "Access-Control-Allow-Origin" for k, v in hdrs)   # local by default


def test_cors_on_emits_headers():
    h = _fake_handler(True)
    hdrs = []
    h.send_header = lambda k, v: hdrs.append((k, v))
    h._cors()
    assert ("Access-Control-Allow-Origin", "*") in hdrs


def test_options_preflight_returns_204_with_cors():
    h = _fake_handler(True)
    calls = {"resp": None, "end": False, "hdrs": []}
    h.send_response = lambda c: calls.__setitem__("resp", c)
    h.send_header = lambda k, v: calls["hdrs"].append((k, v))
    h.end_headers = lambda: calls.__setitem__("end", True)
    h.do_OPTIONS()
    assert calls["resp"] == 204 and calls["end"] is True
    assert ("Access-Control-Allow-Origin", "*") in calls["hdrs"]


def test_flatten_messages():
    sys_, prompt = gateway._flatten_messages([
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "hello"}])
    assert sys_ == "be brief" and prompt == "hello"
    _, p2 = gateway._flatten_messages([{"role": "user", "content": [{"type": "text", "text": "hi"}]}])
    assert p2 == "hi"                              # OpenAI content-parts array flattens


def test_flatten_messages_multi_turn_keeps_history():
    sys_, prompt = gateway._flatten_messages([
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "what is 2+2?"},
        {"role": "assistant", "content": "4"},
        {"role": "user", "content": "and times 3?"}])
    assert sys_ == "be brief"
    # the whole conversation is present, not just the last line
    assert "what is 2+2?" in prompt and "4" in prompt and "and times 3?" in prompt
    assert prompt.rstrip().endswith("Assistant:")   # primes the next turn
    assert "User:" in prompt and "Assistant:" in prompt


def test_openai_models_lists_flywheel_and_roster():
    m = gateway.openai_models()
    assert m["object"] == "list"
    ids = {d["id"] for d in m["data"]}
    assert "flywheel" in ids and len(ids) > 5      # the verified seat + the full roster
    assert all(d["object"] == "model" for d in m["data"])


def test_openai_chat_returns_openai_shape_with_receipt(monkeypatch):
    monkeypatch.setattr(gateway, "_resolve_proposer",
                        lambda model, serve_url: (_OneProposer("hi from the model"), None, 200))
    req = {"model": "flywheel", "messages": [{"role": "user", "content": "say hi"}]}
    body, code, receipt, text, mref = gateway.openai_chat(req, "http://x")
    assert code == 200
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"] == {"role": "assistant", "content": "hi from the model"}
    assert body["choices"][0]["finish_reason"] == "stop"
    assert body["id"].startswith("chatcmpl-")
    assert body["x_receipt"]["receipt_id"] and "usage" in body
    # the receipt is the same content-addressed one, re-checkable
    from harness.messages_api import make_receipt
    expect = make_receipt({"prompt": "say hi", "system": "", "max_new_tokens": 512,
                           "temperature": 0.0, "seed": 0},
                          {"text": "hi from the model", "seed": 0, "prompt_hash": "h"}, "stub")
    assert body["x_receipt"]["receipt_id"] == expect["receipt_id"]


class _Raiser:
    model_ref = "down-provider"
    def generate(self, *a, **k):
        raise RuntimeError("provider down")


def test_openai_chat_failover_tries_next_on_error(monkeypatch):
    def resolver(model, serve_url):
        if model == "p1": return _Raiser(), None, 200
        if model == "p2": return _OneProposer("answer from p2"), None, 200
        return None, "unknown", 404
    monkeypatch.setattr(gateway, "_resolve_proposer", resolver)
    body, code, receipt, text, mref = gateway.openai_chat(
        {"model": "p1,p2", "messages": [{"role": "user", "content": "hi"}]}, "http://x")
    assert code == 200 and text == "answer from p2"
    assert receipt["routed_via"] == "p2"                       # the one that actually answered
    assert any("p1" in t for t in receipt["failover_from"])    # records the skipped primary


def test_openai_chat_failover_skips_absent_credential(monkeypatch):
    def resolver(model, serve_url):
        if model == "openai": return None, "no credential present", 400
        if model == "serve": return _OneProposer("local answer"), None, 200
        return None, "unknown", 404
    monkeypatch.setattr(gateway, "_resolve_proposer", resolver)
    body, code, receipt, text, mref = gateway.openai_chat(
        {"model": "openai,serve", "messages": [{"role": "user", "content": "hi"}]}, "http://x")
    assert code == 200 and receipt["routed_via"] == "serve"


def test_openai_chat_all_providers_fail(monkeypatch):
    monkeypatch.setattr(gateway, "_resolve_proposer",
                        lambda m, s: (None, "no credential present", 400))
    body, code, *_ = gateway.openai_chat(
        {"model": "a,b", "messages": [{"role": "user", "content": "hi"}]}, "http://x")
    assert code == 400 and "all providers failed" in body["error"]["message"]
    assert len(body["failover_from"]) == 2                     # both attempts recorded


def test_openai_chat_single_model_clean_receipt(monkeypatch):
    monkeypatch.setattr(gateway, "_resolve_proposer",
                        lambda m, s: (_OneProposer("ok"), None, 200))
    body, code, receipt, *_ = gateway.openai_chat(
        {"model": "solo", "messages": [{"role": "user", "content": "hi"}]}, "http://x")
    assert code == 200 and receipt["routed_via"] == "solo"
    assert "failover_from" not in receipt                      # no fallback tried, no noise


def test_openai_chat_no_user_turn_is_400():
    body, code, *_ = gateway.openai_chat(
        {"model": "flywheel", "messages": [{"role": "system", "content": "x"}]}, "http://x")
    assert code == 400 and body["error"]["type"] == "invalid_request_error"


def test_resolve_proposer_unknown_model_404(monkeypatch):
    monkeypatch.setattr(gateway, "_unified_roster",
                        lambda: {"endpoints": [{"name": "real", "credential": "present"}]})
    prop, err, code = gateway._resolve_proposer("no-such-model", "http://x")
    assert code == 404 and prop is None


def test_resolve_proposer_absent_credential_400(monkeypatch):
    monkeypatch.setattr(gateway, "_unified_roster",
                        lambda: {"endpoints": [{"name": "openai", "credential": "absent"}]})
    prop, err, code = gateway._resolve_proposer("openai:gpt-4o", "http://x")
    assert code == 400 and prop is None            # never a silent local fallback


def test_resolve_proposer_default_is_local_serve():
    prop, err, code = gateway._resolve_proposer("", "http://127.0.0.1:9")
    assert code == 200 and err is None
    assert prop.__class__.__name__ == "ServeProposer"


def test_sse_chat_emits_openai_event_stream(monkeypatch):
    import io
    monkeypatch.setattr(gateway, "openai_chat",
                        lambda req, serve_url: ({"ok": 1}, 200, {"receipt_id": "abc123"},
                                                "hello world", "stub-model"))
    h = gateway._Handler.__new__(gateway._Handler)
    h.serve_url = "http://x"
    h.wfile = io.BytesIO()
    h.send_response = lambda *a, **k: None
    h.send_header = lambda *a, **k: None
    h.end_headers = lambda *a, **k: None
    h._sse_chat({"model": "flywheel", "messages": [{"role": "user", "content": "hi"}], "stream": True})
    out = h.wfile.getvalue().decode()
    assert "chat.completion.chunk" in out
    assert "assistant" in out                      # role delta
    assert "hello" in out and "world" in out       # content chunks
    assert "x_receipt" in out and "abc123" in out  # receipt rides the final chunk
    assert out.rstrip().endswith("data: [DONE]")   # OpenAI stream terminator


def test_sse_chat_error_falls_back_to_json(monkeypatch):
    import io
    monkeypatch.setattr(gateway, "openai_chat",
                        lambda req, serve_url: ({"error": {"message": "boom"}}, 502, None, None, None))
    h = gateway._Handler.__new__(gateway._Handler)
    h.serve_url = "http://x"; h.wfile = io.BytesIO()
    sent = {}
    h._json = lambda body, code=200: sent.update(body=body, code=code)
    h._sse_chat({"stream": True})
    assert sent["code"] == 502 and "error" in sent["body"]   # errors are plain JSON, never a half-stream


def test_training_status_route_reports_stopped_when_no_run(tmp_path, monkeypatch):
    # Route is read-only and honest with no run present. Inject a dead-screen probe
    # so the test never shells wsl.
    import harness.training_lane as T
    monkeypatch.setattr(T, "screen_alive", lambda *a, **k: False)
    s = gateway._training_status(str(tmp_path))
    assert s["schema"] == "flywheel.training-status/v1"
    assert s["state"] == "stopped"
    assert s["screen_alive"] is False


def test_training_status_route_degrades_on_runtime_error(monkeypatch):
    # A runtime failure INSIDE the present module (not an import failure) must return
    # an honest error dict, never crash the handler thread with a traceback.
    import harness.training_lane as T
    def boom(*a, **k):
        raise PermissionError("log locked")
    monkeypatch.setattr(T, "training_status", boom)
    out = gateway._training_status("whatever")
    assert "error" in out and "training_status failed" in out["error"]


class _FakeHeaders:
    def __init__(self, cl):
        self._cl = cl

    def get(self, key, default=None):
        return self._cl if key == "Content-Length" else default


def _content_length(cl):
    h = gateway._Handler.__new__(gateway._Handler)   # no socket, just the method
    h.headers = _FakeHeaders(cl)
    return h._content_length()


def test_content_length_guard_rejects_garbage_and_oversize():
    assert _content_length("42") == 42                 # valid
    assert _content_length("0") == 0
    assert _content_length("x") is None                # non-numeric -> 400, not a crash
    assert _content_length("") is None                 # present-but-empty
    assert _content_length("-5") is None               # negative
    assert _content_length(str(gateway._Handler.MAX_BODY + 1)) is None   # oversized


def _agent_post(body: dict, root):
    import io
    raw = json.dumps(body).encode()
    h = gateway._Handler.__new__(gateway._Handler)
    h.path = "/api/agent"
    h.root = root
    h.headers = _FakeHeaders(str(len(raw)))
    h.rfile = io.BytesIO(raw)
    sent = {}
    h._json = lambda b, code=200: sent.update(body=b, code=code)
    h._post()
    return sent


def _fake_spec(base_url="https://api.x.com/v1", api_key_env="X_KEY"):
    s = type("Spec", (), {})()
    s.base_url, s.api_key_env, s.local, s.default_model = base_url, api_key_env, False, "e"
    return s


def test_embeddings_unknown_provider_400():
    body, code = gateway.openai_embeddings({"model": "no-such", "input": "hi"})
    assert code == 400 and "no hosted embeddings provider" in body["error"]["message"]


def test_embeddings_missing_credential_400(monkeypatch):
    from harness import providers
    monkeypatch.setitem(providers.REGISTRY, "xprov", _fake_spec())
    monkeypatch.delenv("X_KEY", raising=False)
    body, code = gateway.openai_embeddings({"model": "xprov", "input": "hi"})
    assert code == 400 and "missing credential" in body["error"]["message"]


def test_embeddings_forwards_to_provider(monkeypatch):
    from harness import providers
    monkeypatch.setitem(providers.REGISTRY, "xprov", _fake_spec())
    monkeypatch.setenv("X_KEY", "secret")
    captured = {}

    class _Resp:
        status = 200

        def read(self):
            return b'{"data":[{"embedding":[0.1,0.2]}]}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(request, timeout=60):
        captured["url"] = request.full_url
        captured["headers"] = list(request.header_items())
        captured["body"] = json.loads(request.data)
        return _Resp()

    monkeypatch.setattr(gateway.urllib.request, "urlopen", fake_urlopen)
    body, code = gateway.openai_embeddings({"model": "xprov:embed-3", "input": "hi", "adaptive": True})
    assert code == 200 and body["data"][0]["embedding"] == [0.1, 0.2]
    assert captured["url"] == "https://api.x.com/v1/embeddings"
    assert any("Bearer secret" in str(v) for _, v in captured["headers"])   # key forwarded
    assert captured["body"]["model"] == "embed-3" and "adaptive" not in captured["body"]


def test_sse_agent_streams_events(monkeypatch):
    import io
    import harness.router_agent as RA

    def fake_run(goal, endpoint, **kw):
        oe = kw["on_event"]
        oe({"type": "assistant", "step": 1, "text": "working"})
        oe({"type": "tool_result", "name": "list_dir", "ok": True, "output": "a\nb"})
        return {"final": "done", "steps": 1, "verified": True, "integrity": {"clean": True}}

    monkeypatch.setattr(RA, "run_router_agent", fake_run)
    h = gateway._Handler.__new__(gateway._Handler)
    h.root = "."
    h.wfile = io.BytesIO()
    h.send_response = lambda *a, **k: None
    h.send_header = lambda *a, **k: None
    h.end_headers = lambda *a, **k: None
    h._cors = lambda: None
    h._sse_agent({"stream": True}, "the goal", "endpoint")
    out = h.wfile.getvalue().decode()
    assert "assistant" in out and "tool_result" in out
    assert '"type": "done"' in out
    assert out.rstrip().endswith("data: [DONE]")


def test_router_stats_endpoint(monkeypatch):
    from harness.router_stats import RouterStats
    rs = RouterStats()
    rs.record("openai", True)
    monkeypatch.setattr(gateway, "_ROUTER_STATS", rs)
    h = gateway._Handler.__new__(gateway._Handler)
    h.path = "/api/router/stats"
    sent = {}
    h._json = lambda b, code=200: sent.update(body=b, code=code)
    h._get()
    assert sent["body"]["schema"] == "flywheel.router-stats/v1"
    assert "openai" in sent["body"]["providers"]


class _SpyStats:
    def __init__(self):
        self.ordered = None
        self.recorded = []

    def order(self, chain):
        self.ordered = list(chain)
        return chain

    def record(self, *a, **k):
        self.recorded.append(a)


def test_openai_chat_adaptive_reorders_and_records(monkeypatch):
    spy = _SpyStats()
    monkeypatch.setattr(gateway, "get_router_stats", lambda: spy)
    monkeypatch.setattr(gateway, "_resolve_proposer", lambda cand, url: (None, "unavailable", 503))
    gateway.openai_chat({"model": "a,b", "adaptive": True,
                         "messages": [{"role": "user", "content": "hi"}]}, "http://x")
    assert spy.ordered == ["a", "b"]          # reorder consulted
    assert len(spy.recorded) == 2             # both failures recorded


def test_openai_chat_default_does_not_touch_stats(monkeypatch):
    spy = _SpyStats()
    monkeypatch.setattr(gateway, "get_router_stats", lambda: spy)
    monkeypatch.setattr(gateway, "_resolve_proposer", lambda cand, url: (None, "unavailable", 503))
    gateway.openai_chat({"model": "a", "messages": [{"role": "user", "content": "hi"}]}, "http://x")
    assert spy.ordered is None and spy.recorded == []   # explicit order honored, no side effect


def test_agent_route_validates_goal_and_endpoint(tmp_path):
    sent = _agent_post({"goal": "", "endpoint": ""}, tmp_path)
    assert sent["code"] == 400 and "goal" in sent["body"]["error"]


def test_agent_route_dispatches_gated_and_caps_steps(tmp_path, monkeypatch):
    import harness.router_agent as RA
    seen = {}

    def fake_run(goal, endpoint, **kw):
        seen.update(goal=goal, endpoint=endpoint, kw=kw)
        return {"final": "done", "steps": 1, "verified": True,
                "checkpoint": "abc", "endpoint": endpoint}

    monkeypatch.setattr(RA, "run_router_agent", fake_run)
    sent = _agent_post({"goal": "fix the bug", "endpoint": "anthropic",
                        "max_steps": 99}, tmp_path)
    assert sent["code"] == 200 and sent["body"]["final"] == "done"
    assert seen["goal"] == "fix the bug" and seen["endpoint"] == "anthropic"
    assert seen["kw"]["max_steps"] == 12               # capped, no runaway loop
    assert seen["kw"]["allow_write"] is False          # default-deny survives the HTTP hop
    assert seen["kw"]["allow_exec"] is False
