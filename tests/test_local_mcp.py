"""Falsifiers for the harness MCP server (agent-consumable over JSON-RPC).

Load-bearing: (1) initialize names the local-agent server; (2) tools/list
advertises health/chat/run; (3) the health tool returns the real tier report;
(4) a chat with no live backend is a typed error, not a crash; (5) unknown
method/tool are typed; (6) the serve loop round-trips JSON-RPC.
"""
import io
import hashlib
import json

import harness.local_mcp as local_mcp
import harness.receipt_operations as receipt_operations
from harness.local_agent import available_backends as _real_backends
from harness.local_mcp import PROTOCOL, __version__, handle, serve
from harness.receipt_proof import build_receipt_proof, route_payload
from harness.transparency_log import merkle_root, verify_inclusion

LEAVES = [format(i, "064x") for i in range(1, 4)]
_FAKE_RECEIPT_LEDGER = {
    "envelopes": [{"sha256": leaf, "name": f"r{i}.json"}
                  for i, leaf in enumerate(LEAVES, start=1)]
}


def _req(method, rid=1, params=None):
    r = {"jsonrpc": "2.0", "method": method}
    if rid is not None:
        r["id"] = rid
    if params is not None:
        r["params"] = params
    return r


def test_initialize_and_tools_list():
    assert handle(_req("initialize"))["result"]["serverInfo"]["name"] == "local-agent"
    tools = {t["name"] for t in handle(_req("tools/list"))["result"]["tools"]}
    assert tools == {"local_agent_health", "local_agent_chat", "local_agent_run",
                     "local-model.status", "local-model.doctor", "receipt.verify_inclusion",
                     "flywheel.context.health", "flywheel.context.capture", "flywheel.context.preflight"}


def test_lane_probe_finds_a_status_tool():
    # The lane roster reads a lane stale when its server exposes no status or
    # doctor tool, which is what local-model reported before these existed.
    # The names are the ones harness/lanes.py::_probe_lane looks for.
    tools = {t["name"] for t in handle(_req("tools/list"))["result"]["tools"]}
    assert {"local-model.status", "local-model.doctor"} & tools


def test_status_is_identity_and_doctor_adds_the_tiers():
    st = json.loads(handle(_req("tools/call", params={
        "name": "local-model.status", "arguments": {}}))["result"]["content"][0]["text"])
    assert st == {"ok": True, "server": "local-model", "version": __version__,
                  "protocol": PROTOCOL}
    doc = json.loads(handle(_req("tools/call", params={
        "name": "local-model.doctor", "arguments": {}}))["result"]["content"][0]["text"])
    assert doc["tiers_configured"] == ["ServeBackend", "OllamaBackend"]
    assert "unprobed" in doc["reachability"]
    assert "local_agent_run" in doc["tools"]


def test_doctor_pings_nothing():
    # The description says network-free. Point both tiers at dead ports: a
    # doctor that probed would stall or report them down, and it does neither.
    import harness.local_mcp as m
    from harness.local_agent import ServeBackend
    calls = []

    def dead(*a, **k):
        calls.append(1)
        return [ServeBackend(base_url="http://127.0.0.1:1")]
    m.__dict__["available_backends"] = dead
    try:
        doc = json.loads(handle(_req("tools/call", params={
            "name": "local-model.doctor", "arguments": {}}))["result"]["content"][0]["text"])
    finally:
        m.__dict__["available_backends"] = _real_backends
    assert doc["tiers_configured"] == ["ServeBackend"] and calls == [1]
    assert "unprobed" in doc["reachability"]


def test_health_tool_returns_tier_report():
    resp = handle(_req("tools/call", params={"name": "local_agent_health", "arguments": {}}))
    report = json.loads(resp["result"]["content"][0]["text"])
    assert "tiers" in report and {t["backend"] for t in report["tiers"]} >= {"serve", "ollama"}


def test_chat_with_no_backend_is_typed_error(monkeypatch):
    # force every backend unhealthy: point at dead local ports and no online
    import harness.local_mcp as m
    from harness.local_agent import ServeBackend

    def dead(*a, **k):
        return [ServeBackend(base_url="http://127.0.0.1:1"),
                ServeBackend(base_url="http://127.0.0.1:2")]
    monkeypatch.setattr(m, "available_backends", dead)
    resp = handle(_req("tools/call", params={"name": "local_agent_chat",
                                             "arguments": {"prompt": "hi"}}))
    assert resp["result"]["isError"] is True


def test_unknown_tool_and_method_are_typed():
    assert handle(_req("tools/call", params={"name": "nope", "arguments": {}}))["result"]["isError"]
    assert handle(_req("bogus"))["error"]["code"] == -32601


def test_serve_loop_roundtrips():
    stdin = io.StringIO(json.dumps(_req("initialize")) + "\n")
    out = io.StringIO()
    serve(stdin=stdin, stdout=out)
    assert json.loads(out.getvalue())["result"]["serverInfo"]["name"] == "local-agent"


def _receipt_call(arguments):
    response = handle(_req("tools/call", params={
        "name": "receipt.verify_inclusion", "arguments": arguments}))
    result = response["result"]
    return result, json.loads(result["content"][0]["text"])


def _use_fake_ledger(monkeypatch):
    monkeypatch.setattr(local_mcp, "_receipt_ledger",
                        lambda: _FAKE_RECEIPT_LEDGER, raising=False)


def test_receipt_tool_is_discoverable_with_a_strict_leaf_schema():
    tools = handle(_req("tools/list"))["result"]["tools"]
    tool = next(t for t in tools if t["name"] == "receipt.verify_inclusion")

    schema = tool["inputSchema"]
    assert schema["type"] == "object"
    assert schema["required"] == ["leaf"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["leaf"]["description"]
    assert tool["outputSchema"]["required"] == [
        "included", "status", "proof", "verification", "does_not_prove"]
    assert {case["properties"]["status"]["const"]
            for case in tool["outputSchema"]["oneOf"]} == {
                "included", "missing", "proof_corrupt",
                "proof_leaf_mismatch"}
    included = next(case for case in tool["outputSchema"]["oneOf"]
                    if case["properties"]["status"]["const"] == "included")
    assert included["properties"]["proof"]["required"] == [
        "schema", "leaf", "index", "tree_size", "merkle_root", "audit_path"]
    assert included["properties"]["verification"]["required"] == [
        "method", "replayed", "included"]
    http = tool["x-flywheel-transport-availability"]["http"]
    assert http["custody"] == "gateway-configured"
    assert http["auth_policy"] == (
        "gateway handler auth applies when configured; route is not "
        "private-custody")


def test_receipt_mcp_included_leaf_returns_replayable_proof(monkeypatch):
    _use_fake_ledger(monkeypatch)

    result, payload = _receipt_call({"leaf": LEAVES[1]})

    assert not result.get("isError", False)
    assert result["structuredContent"] == payload
    assert payload["included"] is True
    assert payload["status"] == "included"
    proof = payload["proof"]
    http_body, http_status = route_payload(LEAVES[1], LEAVES)
    assert http_status == 200
    assert proof == http_body
    assert proof["schema"] == "flywheel.receipts-proof/v2"
    assert verify_inclusion(
        proof["leaf"], proof["audit_path"], proof["merkle_root"]) is True
    assert payload["verification"] == {
        "method": "harness.transparency_log.verify_inclusion",
        "replayed": True,
        "included": True,
    }
    assert "semantic correctness" in " ".join(payload["does_not_prove"])
    assert "evidence completeness" in " ".join(payload["does_not_prove"])


def test_receipt_mcp_missing_leaf_keeps_absence_distinct_from_malformed(
        monkeypatch):
    _use_fake_ledger(monkeypatch)
    stranger = "f" * 64

    result, payload = _receipt_call({"leaf": stranger})

    assert not result.get("isError", False)
    assert payload["included"] is False
    assert payload["status"] == "missing"
    assert payload["reason"] == "leaf not in the receipts log"
    assert payload["proof"] == {
        "leaf": stranger,
        "merkle_root": merkle_root(LEAVES),
    }
    assert "semantic correctness" in " ".join(payload["does_not_prove"])


def test_receipt_mcp_malformed_leaf_is_a_typed_error(monkeypatch):
    _use_fake_ledger(monkeypatch)

    result, payload = _receipt_call({"leaf": "short"})

    assert result["isError"] is True
    assert result["structuredContent"] == payload
    assert payload == {"error": {
        "code": "INVALID_LEAF",
        "message": "leaf must be a 64-hex sha256 digest",
    }}


def test_receipt_mcp_rejects_corrupt_provider_results(monkeypatch):
    _use_fake_ledger(monkeypatch)
    bad_root = build_receipt_proof(LEAVES[1], LEAVES)
    bad_root["merkle_root"] = "0" * 64
    bad_meta = build_receipt_proof(LEAVES[1], LEAVES)
    bad_meta.update({"schema": "not-v2", "index": 0, "tree_size": 999})
    failed_proof = {"leaf": LEAVES[1], "merkle_root": merkle_root(LEAVES),
                    "audit_path": []}
    cases = [
        ({"included": True, "proof": bad_root}, "proof did not replay"),
        ({"included": True, "proof": bad_meta},
         "proof object does not match ledger"),
        ({"included": False, "proof": failed_proof},
         "provider returned failed proof material"),
    ]
    for returned, reason in cases:
        monkeypatch.setattr(
            receipt_operations, "dispatch",
            lambda name, arguments, **kwargs: returned)
        result, payload = _receipt_call({"leaf": LEAVES[1]})
        assert not result.get("isError", False)
        assert payload["included"] is False
        assert payload["status"] == "proof_corrupt"
        assert payload["reason"] == reason


def test_receipt_mcp_refuses_valid_proof_for_a_different_requested_leaf(
        monkeypatch):
    _use_fake_ledger(monkeypatch)
    proof = build_receipt_proof(LEAVES[0], LEAVES)

    def mismatched_dispatch(name, arguments, **kwargs):
        assert name == "verify_receipt_inclusion"
        assert arguments == {"leaf": LEAVES[1]}
        return {"included": True, "proof": proof}

    monkeypatch.setattr(receipt_operations, "dispatch", mismatched_dispatch)

    result, payload = _receipt_call({"leaf": LEAVES[1]})

    assert not result.get("isError", False)
    assert payload["included"] is False
    assert payload["status"] == "proof_leaf_mismatch"
    assert payload["reason"] == "proof leaf does not match requested leaf"


def test_receipt_mcp_cli_serve_loop_uses_configured_run_root(
        tmp_path, monkeypatch):
    from harness import local_agent_cli

    run_root = tmp_path / "configured-run"
    env_dir = run_root / "envelopes"
    env_dir.mkdir(parents=True)
    body = {"verdict": "PASS", "task_id": "configured"}
    raw = json.dumps(body, sort_keys=True).encode()
    (env_dir / "configured.json").write_bytes(raw)
    leaf = hashlib.sha256(raw).hexdigest()
    stdin = io.StringIO(json.dumps(_req("tools/call", params={
        "name": "receipt.verify_inclusion",
        "arguments": {"leaf": leaf}})) + "\n")
    stdout = io.StringIO()

    monkeypatch.setattr(local_agent_cli.sys, "stdin", stdin)
    monkeypatch.setattr(local_agent_cli.sys, "stdout", stdout)
    assert local_agent_cli.main([
        "--mcp", "--root", str(tmp_path), "--run-root", str(run_root)]) == 0
    result = json.loads(stdout.getvalue())["result"]
    payload = json.loads(result["content"][0]["text"])
    http_body, http_status = route_payload(leaf, [leaf])

    assert http_status == 200
    assert result["structuredContent"] == payload
    assert payload["included"] is True
    assert payload["proof"] == http_body


def test_receipt_mcp_hides_unexpected_operation_errors(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise RuntimeError("secret ledger detail")

    monkeypatch.setattr(receipt_operations, "dispatch", unavailable)

    result, payload = _receipt_call({"leaf": LEAVES[1]})

    assert result["isError"] is True
    assert payload == {"error": {
        "code": "RECEIPTS_LEDGER_UNAVAILABLE",
        "message": "the receipts ledger could not be read",
    }}
    assert "secret" not in json.dumps(result)
