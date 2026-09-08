import json
import io

from harness.gateway_grant_route import (
    authorize_gateway_operation, gateway_grant_post,
)
from harness.journey_store import JourneyStore, MutationCommand
from harness.source_context_route import source_context_post

OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "a" * 32
NOW = "2026-09-08T12:00:00Z"


class NoopGuard:
    calls = []
    def __init__(self, path): self.path = path
    def __enter__(self):
        type(self).calls.append(str(self.path))
        return self
    def __exit__(self, *_): return False
    def identity(self): return {"platform": "test", "file_index": len(type(self).calls)}


class FakeGather:
    def __init__(self): self.calls = []
    def inspect(self, path, **caps):
        self.calls.append(("inspect", str(path), caps))
        return {"schema": "gather.readable-corpus/v1", "corpus_digest": "c" * 64,
                "rows": [{"row_ref": "row_abc", "body_status": "MATCH",
                          "excerpt": "DECISION", "omissions": []}],
                "omissions": [], "does_not_prove": ["truth"],
                "row_count": 1, "returned_rows": 1, "verified": True,
                "verified_scope": "corpus"}
    def select(self, path, selections, *, expected_corpus_digest, **caps):
        self.calls.append(("select", str(path), selections, expected_corpus_digest, caps))
        return {"schema": "gather.readable-context/v1", "corpus_digest": expected_corpus_digest,
                "selection_digest": "d" * 64, "selection_count": 1,
                "selections": [{"row_ref": "row_abc", "kind": "document", "id": "alpha",
                    "title": "Private title", "source": "docs", "ref": "private/ref",
                    "method": "file-read", "sha256": "e" * 64,
                    "verified_sha256": "f" * 64, "derived_from": [],
                    "full_text_chars": 64, "body_bytes_read": 64,
                    "range": {"start": 0, "end": 19},
                    "text": "DECISION-FACT-ALPHA", "omissions": []}],
                "omissions": [], "does_not_prove": ["truth"],
                "verified": True, "verified_scope": "selected_rows"}


def _corpus_root(state):
    root = state / "source-context" / "corpora" / OWNER / "demo" / "tiny"
    root.mkdir(parents=True)
    return root


def test_attach_route_publishes_ref_and_gateway_prepare_validates_same_owner(tmp_path):
    _corpus_root(tmp_path)
    gather = FakeGather()
    body, status = source_context_post("/api/source-context/attach", json.dumps({
        "schema": "flywheel.source-context-request/v1", "root_mode": "flywheel_corpus",
        "profile": "demo", "corpus": "tiny", "expected_corpus_digest": "c" * 64,
        "selections": [{"row_ref": "row_abc", "start": 0, "limit": 19}],
    }).encode(), owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW,
        gather=gather, guard_cls=NoopGuard)

    assert status == 200
    ref = body["source_context_ref"]
    assert ref.startswith("data_source_context.")
    assert "DECISION-FACT-ALPHA" not in json.dumps(body["projection"])
    assert gather.calls[0][0] == "select"

    head = JourneyStore(tmp_path).create(MutationCommand(
        OWNER, JOURNEY, None, "create", "intake",
        {"legacy_label": None, "goal": "run", "intake": {}, "occurred_at": NOW})).event_head_sha256
    proposal, p_status = gateway_grant_post("/api/gateway-grants/prepare/agent.run", json.dumps({
        "schema": "flywheel.gateway-operation/v1", "journey_ref": JOURNEY,
        "expected_event_head": head, "client_request_id": "request-1",
        "operation": {"goal": "use source", "endpoint": "local", "max_steps": 1,
            "allow_write": False, "allow_exec": False, "stream": True,
            "data_refs": [ref], "credential_refs": []},
    }).encode(), owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
    assert p_status == 200
    assert proposal["data_refs"] == [ref]
    approved, a_status = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": proposal["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
    assert a_status == 200
    authorized = authorize_gateway_operation("agent.run", json.dumps({
        "schema": "flywheel.gateway-operation/v1", "journey_ref": JOURNEY,
        "expected_event_head": head, "client_request_id": "request-1",
        "grant_ref": approved["grant_ref"], "goal": "use source",
        "endpoint": "local", "max_steps": 1, "allow_write": False,
        "allow_exec": False, "stream": True, "data_refs": [ref],
        "credential_refs": []}).encode(), owner_ref=OWNER,
        state_root=tmp_path, clock=lambda: NOW)
    captured = []
    class Launched:
        def resume(self): return True
        def wait(self, _timeout): return None
        def close(self): pass
    from harness.gateway_operation_process import GatewayAgentProcessFactory
    GatewayAgentProcessFactory(
        repo_root=tmp_path, run_root=tmp_path, state_root=tmp_path,
        launcher=lambda spec: captured.append(spec) or Launched()).create(
            authorized, lambda _event: None)
    worker_payload = captured[0].stdin_bytes.decode("utf-8")
    assert "DECISION-FACT-ALPHA" in worker_payload
    assert "private/ref" not in worker_payload

    other, other_status = gateway_grant_post("/api/gateway-grants/prepare/agent.run", json.dumps({
        "schema": "flywheel.gateway-operation/v1", "journey_ref": JOURNEY,
        "expected_event_head": head, "client_request_id": "request-2",
        "operation": {"goal": "use source", "endpoint": "local", "max_steps": 1,
            "allow_write": False, "allow_exec": False, "stream": True,
            "data_refs": [ref], "credential_refs": []},
    }).encode(), owner_ref="owner_" + "b" * 32, state_root=tmp_path, clock=lambda: NOW)
    assert other_status == 403
    assert other["error"]["code"] == "SOURCE_CONTEXT_PERMISSION_DENIED"


def test_workspace_mode_is_unavailable_without_reading_gather(tmp_path):
    gather = FakeGather()
    body, status = source_context_post("/api/source-context/inspect", json.dumps({
        "schema": "flywheel.source-context-request/v1", "root_mode": "workspace",
        "profile": "demo", "corpus": "tiny",
    }).encode(), owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW,
        gather=gather, guard_cls=NoopGuard)
    assert status == 409
    assert body["error"]["code"] == "SOURCE_CONTEXT_AUTHORITY_UNAVAILABLE"
    assert gather.calls == []


def test_gateway_handler_routes_source_context_attach(monkeypatch, tmp_path):
    import harness.gateway as gateway
    import harness.source_context_route as route
    state = tmp_path / "state"
    corpus = state / "source-context" / "corpora" / OWNER / "demo" / "tiny"
    corpus.mkdir(parents=True)
    class FakeAdapter:
        last_identity = {"platform": "test", "file_index": 7}
        def __init__(self, **_kwargs): pass
        def select(self, path, selections, *, expected_corpus_digest, **_caps):
            assert str(path).endswith("tiny")
            return FakeGather().select(
                path, selections,
                expected_corpus_digest=expected_corpus_digest)
    monkeypatch.setattr(route, "GatherPathAdapter", FakeAdapter)
    monkeypatch.setattr(gateway._Handler, "flywheel_home", tmp_path,
                        raising=False)
    monkeypatch.setattr(gateway._Handler, "owner_ref", OWNER, raising=False)
    monkeypatch.setattr(gateway._Handler, "clock", lambda *a: NOW,
                        raising=False)
    raw = json.dumps({"schema": "flywheel.source-context-request/v1",
        "root_mode": "flywheel_corpus", "profile": "demo", "corpus": "tiny",
        "expected_corpus_digest": "c" * 64,
        "selections": [{"row_ref": "row_abc", "start": 0, "limit": 19}]}).encode()
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = "/api/source-context/attach"
    handler.headers = type("H", (), {"get": lambda _s, k, d=None:
        str(len(raw)) if k == "Content-Length" else d})()
    handler.rfile, sent = io.BytesIO(raw), {}
    handler._json = lambda body, code=200: sent.update(body=body, code=code)

    handler._post()

    assert sent["code"] == 200
    assert sent["body"]["source_context_ref"].startswith("data_source_context.")
