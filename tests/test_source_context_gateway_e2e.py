import json
from dataclasses import replace

import pytest

from harness.cross_harness_process import ProcessOutcome
from harness.gateway_grant_route import gateway_grant_post
from harness.gateway_operation_process import GatewayAgentProcessFactory
from harness.gateway_operation_route import route_gateway_operation
from harness.gateway_operations import GatewayOperations
from harness.journey_store import JourneyStore, MutationCommand
from harness.source_context_route import admit_flywheel_corpus, source_context_post
from tests.test_source_context_route import JOURNEY, NOW, OWNER


def test_real_gather_source_context_to_gateway_stub_provider_durable_trace(tmp_path):
    context = pytest.importorskip("gather.context")
    item = pytest.importorskip("gather.item")
    store = pytest.importorskip("gather.store")
    if not all(hasattr(context, name) for name in ("inspect_corpus", "select_context")):
        pytest.skip("Gather readable-context path API is unavailable")
    corpus_path = tmp_path / "source-context" / "corpora" / OWNER / "demo" / "tiny"
    corpus = store.Corpus(str(corpus_path), fsync=False)
    corpus.add([item.make_item(kind="document", id="alpha", title="Alpha",
        text="0123456789DECISION-FACT-ALPHA\nnaïve café", source="docs",
        ref="alpha-private-ref", method="file-read", fetched_at=1.0),
        item.make_item(kind="document", id="distractor", title="Distractor",
        text="DISTRACTOR-UNSELECTED", source="docs", ref="distractor",
        method="file-read", fetched_at=1.0)])
    admit_flywheel_corpus(tmp_path, OWNER, "demo", "tiny", clock=lambda: NOW)

    inspected, inspect_status = source_context_post(
        "/api/source-context/inspect", json.dumps({
            "schema": "flywheel.source-context-request/v1",
            "root_mode": "flywheel_corpus", "profile": "demo", "corpus": "tiny",
            "max_rows": 2}).encode(), owner_ref=OWNER, state_root=tmp_path,
        clock=lambda: NOW)
    assert inspect_status == 200
    row_ref = next(row["row_ref"] for row in inspected["rows"] if row["id"] == "alpha")
    attached, attach_status = source_context_post(
        "/api/source-context/attach", json.dumps({
            "schema": "flywheel.source-context-request/v1",
            "root_mode": "flywheel_corpus", "profile": "demo", "corpus": "tiny",
            "expected_corpus_digest": inspected["corpus_digest"],
            "selections": [{"row_ref": row_ref, "start": 10, "limit": 25}]}).encode(),
        owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
    assert attach_status == 200
    ref = attached["source_context_ref"]

    head = JourneyStore(tmp_path).create(MutationCommand(
        OWNER, JOURNEY, None, "create", "intake",
        {"legacy_label": None, "goal": "source e2e", "intake": {},
         "occurred_at": NOW})).event_head_sha256
    operation = {"goal": "answer from selected context", "endpoint": "stub",
        "max_steps": 1, "allow_write": False, "allow_exec": False,
        "stream": False, "data_refs": [ref], "credential_refs": []}
    proposal, p_status = gateway_grant_post(
        "/api/gateway-grants/prepare/agent.run", json.dumps({
            "schema": "flywheel.gateway-operation/v1", "journey_ref": JOURNEY,
            "expected_event_head": head, "client_request_id": "source-e2e",
            "operation": operation}).encode(), owner_ref=OWNER,
        state_root=tmp_path, clock=lambda: NOW)
    approved, a_status = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": proposal["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
    assert (p_status, a_status) == (200, 200)

    captures = []
    class StubProcess:
        def resume(self): return True
        def signal_tree(self): return True
        def close(self): pass
        def wait(self, _timeout):
            private = json.loads(captures[0].stdin_bytes)
            source = private["source_context"]
            text = source["contexts"][0]["rows"][0]["text"]
            assert text == "DECISION-FACT-ALPHA\nnaïve"
            assert "alpha-private-ref" not in json.dumps(source)
            result = {"final": "provider-stub consumed selected source",
                      "source_payload_sha256": source["source_payload_sha256"]}
            output = "\n".join((json.dumps({"type": "progress",
                "event": {"provider": "stub", "source_context_ref": ref}}),
                json.dumps({"type": "terminal", "state": "completed",
                            "result": result}), ""))
            return ProcessOutcome(0, output, "", 1, False)
    def launcher(spec):
        captures.append(spec)
        return StubProcess()
    service = GatewayOperations(tmp_path, clock=lambda: NOW, lock_timeout_s=5,
        credential_resolver=lambda authorized, _root: replace(
            authorized, credential_bindings={}))
    raw = json.dumps({"schema": "flywheel.gateway-operation/v1",
        "journey_ref": JOURNEY, "expected_event_head": head,
        "client_request_id": "source-e2e", "grant_ref": approved["grant_ref"],
        **operation}).encode()
    response = route_gateway_operation(
        "POST", "/api/agent", owner_ref=OWNER, raw=raw,
        content_type="application/json", service=service,
        process_factory=GatewayAgentProcessFactory(
            repo_root=tmp_path, run_root=tmp_path, state_root=tmp_path,
            launcher=launcher))

    assert response.status == 200
    assert response.body["final"] == "provider-stub consumed selected source"
    operation_ref = next(iter(service.operation_refs(OWNER)))
    result = service.result(OWNER, operation_ref)
    history = service._history(service._journey(OWNER), operation_ref)
    assert result["state"] == "completed"
    assert any(event["event_type"] == "operation_completed" for event in history)
    public_trace = json.dumps({"history": history, "result": result})
    assert "DECISION-FACT-ALPHA" not in public_trace
    assert "alpha-private-ref" not in public_trace
    assert "DISTRACTOR-UNSELECTED" not in captures[0].stdin_bytes.decode("utf-8")



