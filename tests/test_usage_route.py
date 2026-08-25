"""Tests for the usage-metering route: the offline verify handler, the session
summary roll-up (priced and unpriced kept separate), the gateway's thin stubs
(socketless), and the emit-on-route hook -- a routed answer through a monkeypatched
proposer must write a usage receipt that re-verifies, with no real model."""
import io
import json

from harness import gateway, usage_route
from harness.proposer import ProposerOutput
from harness.usage_route import (
    emit_route_usage,
    handle_usage_summary,
    handle_usage_verify,
)


# --- direct handler tests ----------------------------------------------------


def _emit(run_root, endpoint, model_ref, text, usage, prompt="a prompt"):
    body = {"endpoint": endpoint, "model_ref": model_ref, "text": text,
            "receipt": {"receipt_id": "rid-" + endpoint}, "usage": usage}
    return emit_route_usage(body, run_root, prompt)


def test_summary_rolls_up_and_keeps_priced_and_unpriced_separate(tmp_path):
    # one priced (hosted, provider tokens) + one unpriced (local, provider tokens)
    _emit(tmp_path, "openai", "openai:gpt-4o-mini", "hello there",
          {"prompt": 1000, "completion": 500, "total": 1500})
    _emit(tmp_path, "ollama", "ollama", "local reply",
          {"prompt": 40, "completion": 20, "total": 60})
    body, code = handle_usage_summary("", tmp_path)
    assert code == 200
    assert body["n"] == "2"
    assert body["total_tokens"] == {"prompt": "1040", "completion": "520", "total": "1560"}
    # exactly one carried a dollar amount; the local one is counted unpriced
    assert body["priced_total"]["n"] == "1"
    assert body["priced_total"]["amount"] != ""
    assert body["unpriced_count"] == "1"
    assert set(body["by_endpoint"]) == {"openai", "ollama"}
    assert body["by_endpoint"]["openai"]["total"] == "1500"
    # the summary hands back the receipts themselves so a client re-verifies them
    assert len(body["receipts"]) == 2


def test_provider_reported_vs_estimated_source_labels(tmp_path):
    # provider returned usage on a hosted priced model -> provider_reported
    fn = _emit(tmp_path, "openai", "openai:gpt-4o-mini", "hi",
               {"prompt": 100, "completion": 50, "total": 150})
    r = json.loads((tmp_path / "usage" / fn).read_text(encoding="utf-8"))
    assert r["source"] == "provider_reported"
    assert r["cost"]["amount"] != ""
    # no provider usage -> the tokens are a labeled estimate, never reported
    fn2 = _emit(tmp_path, "openai", "openai:gpt-4o-mini", "hi", None,
                prompt="some prompt text")
    r2 = json.loads((tmp_path / "usage" / fn2).read_text(encoding="utf-8"))
    assert r2["source"] == "estimated"
    # a local endpoint records no dollar figure
    fn3 = _emit(tmp_path, "ollama", "ollama", "reply",
                {"prompt": 10, "completion": 5, "total": 15})
    r3 = json.loads((tmp_path / "usage" / fn3).read_text(encoding="utf-8"))
    assert r3["source"] == "unpriced_local" and r3["cost"]["amount"] == ""


def test_verify_round_trip_match_and_corrupt_one_byte_is_tampered(tmp_path):
    fn = _emit(tmp_path, "openai", "openai:gpt-4o-mini", "hello",
               {"prompt": 1000, "completion": 500, "total": 1500})
    receipt = json.loads((tmp_path / "usage" / fn).read_text(encoding="utf-8"))
    good, code = handle_usage_verify({"receipt": receipt})
    assert code == 200 and good["verdict"] == "MATCH"
    # flip one hex char of the seal on a copy -> the same verifier refuses
    corrupt = json.loads(json.dumps(receipt))
    hexv = corrupt["seal"]["hex"]
    corrupt["seal"]["hex"] = ("1" if hexv[0] == "0" else "0") + hexv[1:]
    bad, _ = handle_usage_verify({"receipt": corrupt})
    assert bad["verdict"] == "TAMPERED" and bad["failure_class"] == "SEAL_MISMATCH"


def test_emit_is_defensive_when_run_root_is_missing():
    assert emit_route_usage({"endpoint": "x"}, None, "p") == ""
    assert emit_route_usage("not a dict", "/tmp", "p") == ""


# --- gateway dispatch (socketless) -------------------------------------------


class _Headers:
    def __init__(self, cl):
        self._cl = cl

    def get(self, key, default=None):
        return self._cl if key == "Content-Length" else default


def _post(path, body, run_root):
    raw = json.dumps(body).encode()
    h = gateway._Handler.__new__(gateway._Handler)
    h.path = path
    h.root = "."
    h.run_root = str(run_root)
    h.headers = _Headers(str(len(raw)))
    h.rfile = io.BytesIO(raw)
    sent = {}
    h._json = lambda b, code=200: sent.update(body=b, code=code)
    h._post()
    return sent


def _get(path, run_root):
    h = gateway._Handler.__new__(gateway._Handler)
    h.path = path
    h.root = "."
    h.run_root = str(run_root)
    sent = {}
    h._json = lambda b, code=200: sent.update(body=b, code=code)
    h._get()
    return sent


class _UsageProposer:
    model_ref = "stub:model"

    def generate(self, prompt, *, seed, temperature, max_new_tokens, system=""):
        return ProposerOutput("routed reply", "stub:model", seed, "h", "stub",
                              usage={"prompt": 1200, "completion": 300, "total": 1500})


def _granted(monkeypatch):
    """The route is grant-gated: authorize returns a test-bound
    operation carrying the posted body, with the frozen execution plan,
    exactly as an approved grant would deliver it."""
    import json as _json
    from harness.gateway_operation import AuthorizedOperation
    from harness.gateway_provider_adapter import freeze_execution_plan

    def fake(action_name, raw, *, owner_ref, state_root, clock):
        envelope = _json.loads(raw)
        op = {k: v for k, v in envelope.items()
              if k not in ('schema', 'journey_ref', 'expected_event_head',
                           'client_request_id', 'grant_ref')}
        authorized = AuthorizedOperation.for_test(action=action_name,
                                                  operation=op,
                                                  scopes=('network',))
        import dataclasses
        plan = freeze_execution_plan(authorized, owner_ref=owner_ref,
                                     state_root=state_root)
        return dataclasses.replace(authorized, execution_plan=plan)

    monkeypatch.setattr(
        'harness.gateway_grant_route.authorize_gateway_operation', fake)


def test_gateway_route_answer_emits_a_verifying_usage_receipt(tmp_path, monkeypatch):
    _granted(monkeypatch)
    # no real model: a monkeypatched roster + proposer, and a no-op scaffold.
    import harness.endpoint_registry as er
    import harness.scaffold as sc
    monkeypatch.setattr(gateway, "_unified_roster",
                        lambda: {"endpoints": [{"name": "stub", "credential": "local-none"}],
                                 "usable_names": ["stub"]})
    monkeypatch.setattr(er, "make_endpoint_proposer",
                        lambda name, **kw: _UsageProposer())
    monkeypatch.setattr(sc, "scaffold_turn", lambda p: {})
    monkeypatch.setattr(sc, "scaffold_answer",
                        lambda text, env, provenance=None: {"ok": True})

    sent = _post("/api/route", {"prompt": "hi there", "endpoint": "stub"}, tmp_path)
    assert sent["code"] == 200
    fn = sent["body"]["usage_receipt_file"]
    assert fn.startswith("usage-receipt-") and fn.endswith(".json")
    # the provider's tokens rode the receipt, and it re-verifies offline
    receipt = json.loads((tmp_path / "usage" / fn).read_text(encoding="utf-8"))
    assert receipt["tokens"] == {"prompt": "1200", "completion": "300", "total": "1500"}
    checked = _post("/api/usage/verify", {"receipt": receipt}, tmp_path)
    assert checked["code"] == 200 and checked["body"]["verdict"] == "MATCH"

    # and the session summary GET sees it
    summ = _get("/api/usage", tmp_path)
    assert summ["code"] == 200 and summ["body"]["n"] == "1"
    assert summ["body"]["total_tokens"]["total"] == "1500"


def test_gateway_usage_verify_stub_returns_the_verdict(tmp_path):
    fn = _emit(tmp_path, "openai", "openai:gpt-4o-mini", "hello",
               {"prompt": 100, "completion": 50, "total": 150})
    receipt = json.loads((tmp_path / "usage" / fn).read_text(encoding="utf-8"))
    sent = _post("/api/usage/verify", {"receipt": receipt}, tmp_path)
    assert sent["code"] == 200 and sent["body"]["verdict"] == "MATCH"


def test_gateway_usage_summary_empty_is_honest(tmp_path):
    sent = _get("/api/usage", tmp_path)
    assert sent["code"] == 200
    assert sent["body"]["n"] == "0"
    assert sent["body"]["receipts"] == []
    assert sent["body"]["unpriced_count"] == "0"
