import json
import os
from pathlib import Path
import textwrap
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
    store.Corpus(str(corpus_path), fsync=False).add([item.make_item(
        kind="document", id="changed", title="Changed",
        text="CHANGED-LIVE-SOURCE-AFTER-APPROVAL", source="docs",
        ref="changed-private-ref", method="file-read", fetched_at=2.0)])

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
    assert "CHANGED-LIVE-SOURCE-AFTER-APPROVAL" not in public_trace
    assert "DISTRACTOR-UNSELECTED" not in captures[0].stdin_bytes.decode("utf-8")


@pytest.mark.skipif(os.name != "nt", reason="owned OS process containment is Windows-only")
def test_real_gather_source_context_to_owned_os_child_agent_stub_plumbing(
        tmp_path, monkeypatch):
    pytest.importorskip("gather.context")
    item = pytest.importorskip("gather.item")
    store = pytest.importorskip("gather.store")
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
            "root_mode": "flywheel_corpus", "profile": "demo",
            "corpus": "tiny", "max_rows": 2}).encode(),
        owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
    row_ref = next(row["row_ref"] for row in inspected["rows"] if row["id"] == "alpha")
    attached, attach_status = source_context_post(
        "/api/source-context/attach", json.dumps({
            "schema": "flywheel.source-context-request/v1",
            "root_mode": "flywheel_corpus", "profile": "demo",
            "corpus": "tiny", "expected_corpus_digest": inspected["corpus_digest"],
            "selections": [{"row_ref": row_ref, "start": 10, "limit": 25}]}).encode(),
        owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
    assert (inspect_status, attach_status) == (200, 200)
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
            "expected_event_head": head, "client_request_id": "source-os-child",
            "operation": operation}).encode(), owner_ref=OWNER,
        state_root=tmp_path, clock=lambda: NOW)
    approved, a_status = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": proposal["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
    assert (p_status, a_status) == (200, 200)
    store.Corpus(str(corpus_path), fsync=False).add([item.make_item(
        kind="document", id="changed", title="Changed",
        text="CHANGED-LIVE-SOURCE-AFTER-APPROVAL", source="docs",
        ref="changed-private-ref", method="file-read", fetched_at=2.0)])
    ambient_profile = tmp_path / "ambient-profile"
    ambient_home = tmp_path / "ambient-home"
    ambient_flywheel = tmp_path / "ambient-flywheel"
    ambient_run = tmp_path / "ambient-run"
    worker_profile = tmp_path / "worker-profile"
    monkeypatch.setenv("USERPROFILE", str(ambient_profile))
    monkeypatch.setenv("HOME", str(ambient_home))
    monkeypatch.setenv("FLYWHEEL_HOME", str(ambient_flywheel))
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(ambient_run))
    repo_root = tmp_path / "os-child-repo"
    repo_root.mkdir()
    receipt = repo_root / "provider-receipt.json"
    real_root = Path(__file__).resolve().parents[1]
    selected_marker = "DECISION-FACT-ALPHA\nnaïve"
    repo_root.joinpath("sitecustomize.py").write_text(textwrap.dedent(f"""
        import importlib.abc, importlib.util, json, os, pathlib, sys, types
        sys.path.insert(0, {str(real_root)!r})
        _receipt = pathlib.Path({str(receipt)!r})
        class _StubRouter(importlib.abc.MetaPathFinder, importlib.abc.Loader):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "harness.router_agent":
                    return importlib.util.spec_from_loader(fullname, self)
                return None
            def create_module(self, spec):
                return types.ModuleType(spec.name)
            def exec_module(self, module):
                def run_router_agent(goal, endpoint, **_kwargs):
                    body = {{"pid": os.getpid(), "endpoint": endpoint,
                        "flywheel_home": os.environ.get("FLYWHEEL_HOME"),
                        "flywheel_run_root": os.environ.get("FLYWHEEL_RUN_ROOT"),
                        "home": os.environ.get("HOME"),
                        "userprofile": os.environ.get("USERPROFILE"),
                        "saw_selected": {selected_marker!r} in goal,
                        "saw_private_ref": "alpha-private-ref" in goal,
                        "saw_distractor": "DISTRACTOR-UNSELECTED" in goal}}
                    _receipt.write_text(json.dumps(body, sort_keys=True),
                        encoding="utf-8")
                    if (not body["saw_selected"] or body["saw_private_ref"]
                            or body["saw_distractor"]):
                        raise RuntimeError("source context boundary failed")
                    return {{"final": "os-child agent stub consumed selected source",
                        "source_marker_seen": True}}
                module.run_router_agent = run_router_agent
        sys.meta_path.insert(0, _StubRouter())
        """), encoding="utf-8")
    service = GatewayOperations(tmp_path, clock=lambda: NOW, lock_timeout_s=5,
        credential_resolver=lambda authorized, _root: replace(
            authorized, credential_bindings={}))
    raw = json.dumps({"schema": "flywheel.gateway-operation/v1",
        "journey_ref": JOURNEY, "expected_event_head": head,
        "client_request_id": "source-os-child",
        "grant_ref": approved["grant_ref"], **operation}).encode()

    response = route_gateway_operation("POST", "/api/agent", owner_ref=OWNER,
        raw=raw, content_type="application/json", service=service,
        process_factory=GatewayAgentProcessFactory(repo_root=repo_root,
            run_root=tmp_path / "runs", state_root=tmp_path))

    assert response.status == 200
    assert response.body["final"] == "os-child agent stub consumed selected source"
    child_receipt = json.loads(receipt.read_text(encoding="utf-8"))
    assert child_receipt == {"endpoint": "stub",
        "flywheel_home": str(tmp_path),
        "flywheel_run_root": str(tmp_path / "runs"),
        "home": str(worker_profile), "pid": child_receipt["pid"],
        "saw_distractor": False, "saw_private_ref": False,
        "saw_selected": True, "userprofile": str(worker_profile)}
    assert child_receipt["pid"] != os.getpid()
    operation_ref = next(iter(service.operation_refs(OWNER)))
    public_trace = json.dumps({"history": service._history(
        service._journey(OWNER), operation_ref),
        "result": service.result(OWNER, operation_ref)})
    assert "DECISION-FACT-ALPHA" not in public_trace
    assert "alpha-private-ref" not in public_trace
    assert "CHANGED-LIVE-SOURCE-AFTER-APPROVAL" not in public_trace
    assert not (ambient_profile / ".flywheel" / "store.db").exists()
    assert not (ambient_home / ".flywheel" / "store.db").exists()
    assert not (ambient_flywheel / "store.db").exists()
    assert not (ambient_run / "agent_runs").exists()
    assert not (worker_profile / ".flywheel" / "store.db").exists()
    assert (tmp_path / "store.db").is_file()
    assert list((tmp_path / "runs" / "agent_runs").glob("*.json"))
