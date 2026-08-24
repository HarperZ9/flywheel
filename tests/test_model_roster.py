"""model_roster contract + the gateway's model-switching seams.

The roster must be honest under every failure: default always present and
flagged, absent credential named, unreachable lister named, and none of it
raises. The gateway seams: /api/models validates its param, /api/route
validates 'model' and threads it into the proposer factory.
"""
import io
import json

import harness.gateway as gateway
import harness.model_roster as MR
from harness.proposer import ProposerOutput


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_spec(base_url="https://api.x.com/v1", api_key_env="X_KEY",
               default_model="x-default"):
    s = type("Spec", (), {})()
    s.base_url, s.api_key_env, s.local = base_url, api_key_env, False
    s.default_model = default_model
    return s


# --- list_models ----------------------------------------------------------------


def test_list_models_maps_openai_payload(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=3.0):
        captured["url"] = req.full_url
        return _Resp({"data": [{"id": "telos-coder-14b"}, {"id": "qwen3:8b"}]})

    monkeypatch.setattr(MR.urllib.request, "urlopen", fake_urlopen)
    out = MR.list_models("ollama")
    assert out["endpoint"] == "ollama" and out["reason"] == ""
    assert captured["url"] == "http://127.0.0.1:11434/v1/models"
    rows = {m["id"]: m["default"] for m in out["models"]}
    assert rows == {"telos-coder-14b": "true", "qwen3:8b": "false"}
    assert len(out["models"]) == 2                 # default never duplicated


def test_list_models_sends_bearer_when_credential_present(monkeypatch):
    from harness import providers
    monkeypatch.setitem(providers.REGISTRY, "xprov", _fake_spec())
    monkeypatch.setattr(MR, "_credential", lambda k: "sk-test")
    captured = {}

    def fake_urlopen(req, timeout=3.0):
        captured["auth"] = req.get_header("Authorization")
        return _Resp({"data": [{"id": "x-other"}]})

    monkeypatch.setattr(MR.urllib.request, "urlopen", fake_urlopen)
    out = MR.list_models("xprov")
    assert captured["auth"] == "Bearer sk-test"
    assert out["models"][0] == {"id": "x-default", "default": "true"}


def test_list_models_absent_credential_is_an_honest_null(monkeypatch):
    from harness import providers
    monkeypatch.setitem(providers.REGISTRY, "xprov", _fake_spec())
    monkeypatch.setattr(MR, "_credential", lambda k: "")
    out = MR.list_models("xprov")
    assert out["reason"] == "credential absent"
    assert out["models"] == [{"id": "x-default", "default": "true"}]


def test_list_models_listing_failure_keeps_flagged_default(monkeypatch):
    def boom(req, timeout=3.0):
        raise OSError("connection refused")

    monkeypatch.setattr(MR.urllib.request, "urlopen", boom)
    out = MR.list_models("ollama")
    assert out["models"] == [{"id": "telos-coder-14b", "default": "true"}]
    assert out["reason"].startswith("listing unavailable:")


def test_list_models_unknown_endpoint_never_raises():
    out = MR.list_models("no-such-endpoint")
    assert out["models"] == [] and "unknown endpoint" in out["reason"]


def test_list_models_native_endpoint_reports_roster_default():
    out = MR.list_models("anthropic")
    assert {"id": "claude-sonnet-5", "default": "true"} in out["models"]
    assert out["reason"].startswith("listing unavailable:")


# --- gateway seams --------------------------------------------------------------


class _FakeHeaders:
    def __init__(self, cl):
        self._cl = cl

    def get(self, key, default=None):
        return self._cl if key == "Content-Length" else default


class _OneProposer:
    model_ref = "stub"

    def __init__(self, text):
        self.text = text

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        return ProposerOutput(self.text, self.model_ref, seed, "h", "stub")


def _get(path):
    h = gateway._Handler.__new__(gateway._Handler)
    h.path = path
    sent = {}
    h._json = lambda b, code=200: sent.update(body=b, code=code)
    h._get()
    return sent


def _post(path, body):
    raw = json.dumps(body).encode()
    h = gateway._Handler.__new__(gateway._Handler)
    h.path = path
    h.headers = _FakeHeaders(str(len(raw)))
    h.rfile = io.BytesIO(raw)
    sent = {}
    h._json = lambda b, code=200: sent.update(body=b, code=code)
    h._post()
    return sent


def test_api_models_requires_endpoint_param():
    sent = _get("/api/models")
    assert sent["code"] == 400 and "endpoint" in sent["body"]["error"]


def test_api_models_serves_the_roster(monkeypatch):
    monkeypatch.setattr(
        MR, "list_models",
        lambda name, timeout=3.0: {"endpoint": name, "models": [], "reason": "r"})
    sent = _get("/api/models?endpoint=ollama")
    assert sent["code"] == 200 and sent["body"]["endpoint"] == "ollama"


def test_route_request_threads_model_into_the_proposer_factory(monkeypatch):
    monkeypatch.setattr(
        gateway, "_unified_roster",
        lambda: {"endpoints": [{"name": "local-x", "credential": "local-none"}],
                 "usable_names": ["local-x"]})
    import harness.endpoint_registry as er
    captured = {}

    def factory(name, **kw):
        captured["name"] = name
        captured.update(kw)
        return _OneProposer("ok")

    monkeypatch.setattr(er, "make_endpoint_proposer", factory)
    body, code = gateway.route_request("hi", "local-x", model="qwen3:8b")
    assert code == 200 and captured["model"] == "qwen3:8b"
    captured.clear()
    gateway.route_request("hi", "local-x")         # no override -> no model kwarg
    assert "model" not in captured


def _granted(monkeypatch):
    """The route is grant-gated now: authorize returns a test-bound
    operation carrying the posted body, with the frozen execution plan
    the real authorize path would produce, so the handler reads the
    admitted operation exactly as an approved grant delivers it."""
    import json as _json

    from harness.gateway_operation import AuthorizedOperation
    from harness.gateway_provider_adapter import freeze_execution_plan

    def fake(action_name, raw, *, owner_ref, state_root, clock):
        envelope = _json.loads(raw)
        op = {k: v for k, v in envelope.items()
              if k not in ("schema", "journey_ref", "expected_event_head",
                           "client_request_id", "grant_ref")}
        authorized = AuthorizedOperation.for_test(action=action_name,
                                                  operation=op,
                                                  scopes=("network",))
        plan = freeze_execution_plan(authorized, owner_ref=owner_ref,
                                     state_root=state_root)
        import dataclasses
        return dataclasses.replace(authorized, execution_plan=plan)

    monkeypatch.setattr(
        "harness.gateway_grant_route.authorize_gateway_operation", fake)


def test_route_post_passes_stripped_model(monkeypatch):
    import harness.scaffold as SC
    monkeypatch.setattr(SC, "scaffold_turn", lambda p: {})
    monkeypatch.setattr(SC, "scaffold_answer",
                        lambda text, env, provenance=None: {"ok": True})
    _granted(monkeypatch)
    seen = {}

    def fake_route(prompt, endpoint, model=""):
        seen.update(prompt=prompt, endpoint=endpoint, model=model)
        return {"text": "routed"}, 200

    monkeypatch.setattr(gateway, "route_request", fake_route)
    sent = _post("/api/route",
                 {"prompt": "hi", "endpoint": "ollama", "model": "  m1  "})
    assert sent["code"] == 200 and seen["model"] == "m1"


def test_route_post_oversize_model_is_refused_at_the_grant_boundary():
    # Shape validation moved into the exact-grant operation: an oversize
    # model is refused before any handler or dispatch exists to see it.
    sent = _post("/api/route",
                 {"prompt": "hi", "endpoint": "ollama", "model": "x" * 201})
    assert sent["code"] == 422
    assert sent["body"]["error"]["code"] == "INVALID_REQUEST"


def test_route_post_non_string_model_is_refused_at_the_grant_boundary():
    sent = _post("/api/route", {"prompt": "hi", "endpoint": "ollama", "model": 7})
    assert sent["code"] == 422
    assert sent["body"]["error"]["code"] == "INVALID_REQUEST"
