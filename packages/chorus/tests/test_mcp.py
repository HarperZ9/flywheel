import io
import json

from chorus.mcp import handle_request, call_tool, serve, _tool_defs

VERDICT_TOKENS = {"MATCH", "DRIFT", "UNVERIFIABLE"}


def _call(name, args):
    resp = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": name, "arguments": args}})
    return resp["result"]


def test_initialize_names_the_server():
    resp = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert resp["result"]["serverInfo"]["name"] == "chorus"
    assert resp["result"]["protocolVersion"]


def test_tools_list_exposes_the_surface():
    names = {t["name"] for t in _tool_defs()}
    assert {
        "chorus.status",
        "chorus.doctor",
        "chorus.run",
        "chorus.corpora",
        "chorus.digests",
        "chorus.decision",
    } <= names
    resp = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert resp["result"]["tools"]


def test_status_is_an_envelope_without_a_verdict_token():
    text = call_tool("chorus.status", {})
    env = json.loads(text)
    assert env["tool"] == "chorus"
    assert env["status"] not in VERDICT_TOKENS       # informational, never a verdict


def test_doctor_reports_wired_capabilities_never_a_verdict():
    env = json.loads(call_tool("chorus.doctor", {}))
    assert env["status"] not in VERDICT_TOKENS
    checks = env["native"]["checks"]
    assert checks and all(c["status"] in {"available", "absent"} for c in checks)
    assert all(c["status"] not in VERDICT_TOKENS for c in checks)


def test_run_over_a_corpus_returns_a_verified_digest(tmp_path):
    rows = [{"kind": "comment", "id": "a", "ref": "v", "text": "great sound design",
             "meta": {"like_count": 9}},
            {"kind": "comment", "id": "b", "ref": "v", "text": "loved the sound design",
             "meta": {"like_count": 3}}]
    corpus = tmp_path / "items.json"
    corpus.write_text(json.dumps(rows), encoding="utf-8")
    out = json.loads(call_tool("chorus.run", {"corpus": str(corpus), "verify": True}))
    assert out["n_items"] == 2 and out["verified"] is True


def test_run_over_a_missing_corpus_is_a_named_error(tmp_path):
    result = _call("chorus.run", {"corpus": str(tmp_path / "nope.json")})
    assert result["isError"] is True
    assert "not found" in result["content"][0]["text"]


def test_corpora_and_digests_tools(tmp_path):
    # a corpus dir + a daemon store, so both discovery tools have something to return
    from chorus.daemon import Watchlist, DigestStore, tick
    (tmp_path / "c").mkdir()
    rows = [{"kind": "metadata", "id": "v", "ref": "v", "title": "T", "meta": {}},
            {"kind": "comment", "id": "a", "ref": "v", "text": "great", "meta": {"like_count": 1}}]
    (tmp_path / "c" / "catalog.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    corpora = json.loads(call_tool("chorus.corpora", {"root": str(tmp_path)}))
    assert corpora["corpora"][0]["name"] == "c"

    itemsfile = tmp_path / "items.json"
    itemsfile.write_text(json.dumps([r for r in rows if r["kind"] == "comment"]), encoding="utf-8")
    store = DigestStore(str(tmp_path / "store"))
    tick(Watchlist([str(itemsfile)]), store, clock=lambda: 1.0)
    digests = json.loads(call_tool("chorus.digests", {"store": str(tmp_path / "store")}))
    assert digests["digests"]


def test_decision_tool_returns_source_change_result(tmp_path):
    reference = tmp_path / "reference.json"
    current = tmp_path / "current.json"
    reference.write_text(json.dumps([
        {"kind": "comment", "id": "same", "ref": "workflow", "text": "the reference source is stable",
         "meta": {"like_count": 5}},
    ]), encoding="utf-8")
    current.write_text(json.dumps([
        {"kind": "comment", "id": "same", "ref": "workflow", "text": "the current source changed",
         "meta": {"like_count": 5}},
    ]), encoding="utf-8")

    out = json.loads(call_tool("chorus.decision", {
        "current": str(current),
        "reference": str(reference),
        "task": "Check whether source evidence changed.",
    }))

    assert out["schema"] == "chorus.source-decision/v1"
    assert out["status"] == "DRIFT"
    assert out["changes"]["counts"] == {"added": 0, "removed": 0, "changed": 1, "unchanged": 0}


def test_decision_tool_missing_source_is_typed_result_not_protocol_error(tmp_path):
    reference = tmp_path / "reference.json"
    reference.write_text(json.dumps([
        {"kind": "comment", "id": "same", "ref": "workflow", "text": "reference source",
         "meta": {"like_count": 1}},
    ]), encoding="utf-8")

    result = _call("chorus.decision", {
        "current": str(tmp_path / "missing.json"),
        "reference": str(reference),
        "task": "Check missing source handling.",
    })
    out = json.loads(result["content"][0]["text"])

    assert result["isError"] is False
    assert out["status"] == "UNVERIFIABLE"
    assert out["source_failures"][0]["code"] == "missing_current"


def test_unknown_tool_is_an_error():
    resp = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": "chorus.nope", "arguments": {}}})
    assert "error" in resp


def test_serve_reads_a_line_and_writes_a_response():
    stdin = io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 7, "method": "initialize"}) + "\n")
    stdout = io.StringIO()
    serve(stdin, stdout)
    line = json.loads(stdout.getvalue().strip())
    assert line["id"] == 7 and line["result"]["serverInfo"]["name"] == "chorus"
