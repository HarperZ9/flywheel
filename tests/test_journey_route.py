import json
import io
import socket
import urllib.request

import pytest

from harness.grant_route import grant_post
from harness.journey_route import journey_post
from harness.journey_store import JourneyStore, MutationCommand
from harness import gateway

NOW = "2026-08-14T12:00:00Z"
OWNER = "owner_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
OTHER = "owner_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _route(action, body, state, evidence, owner=OWNER):
    return journey_post(f"/api/journeys/{action}", json.dumps(body).encode(),
        owner_ref=owner, state_root=state, evidence_root=evidence, clock=lambda: NOW)


def _grant(action, body, state, evidence, owner=OWNER):
    proposed, status = grant_post(f"/api/grants/prepare/{action}",
        json.dumps(body).encode(), owner_ref=owner, state_root=state,
        evidence_root=evidence, clock=lambda: NOW)
    assert status == 200, proposed
    approved, status = grant_post("/api/grants/approve-once",
        json.dumps({"proposal_ref": proposed["proposal_ref"]}).encode(),
        owner_ref=owner, state_root=state, evidence_root=evidence, clock=lambda: NOW)
    assert status == 200, approved
    return approved["grant_ref"], proposed


def _created(tmp_path):
    state, evidence = tmp_path / "state", tmp_path / "evidence"
    state.mkdir(); evidence.mkdir()
    (evidence / "intake.json").write_text('{"summary":"bounded"}', encoding="utf-8")
    request = {"goal": "Preserve evidence", "intake_ref": "intake.json",
               "client_request_id": "create-1"}
    grant, _ = _grant("create", request, state, evidence)
    ack, status = _route("create", {**request, "grant_ref": grant}, state, evidence)
    assert status == 200
    return state, evidence, ack


@pytest.mark.parametrize("action,body", [
    ("create", {"goal": "g", "intake_ref": "i", "client_request_id": "r", "grant_ref": "g"}),
    ("list", {}), ("resume", {"journey_ref": "j", "lens": "Rescue"}),
    ("append", {"journey_ref": "j", "expected_event_head": "h", "client_request_id": "r",
                "grant_ref": "g", "command": {"type": "advance_stage"}}),
    ("check", {"journey_ref": "j", "expected_event_head": "h", "client_request_id": "r",
               "grant_ref": "g", "claim_id": "c", "oracle_id": "o",
               "candidate_ref": "c", "context_ref": "x"}),
    ("cancel", {"journey_ref": "j", "expected_event_head": "h", "client_request_id": "r",
                "grant_ref": "g", "operation_ref": "o"}),
    ("export", {"journey_ref": "j", "expected_event_head": "h", "client_request_id": "r",
                "grant_ref": "g", "packet_ref": "p"}),
])
def test_every_action_rejects_client_owned_server_fields(tmp_path, action, body):
    """Admitting timestamps or event facts would let clients forge custody."""
    tmp_path.mkdir(exist_ok=True)
    result, status = _route(action, {**body, "occurred_at": "C:/private/secret"},
                            tmp_path, tmp_path)
    assert status == 400 and result["error"]["code"] == "UNKNOWN_FIELD"
    assert "private" not in json.dumps(result)


def test_create_list_resume_are_durable_owner_scoped_and_lens_only(tmp_path):
    """A rotated token or foreign owner must not alter or discover custody."""
    state, evidence, ack = _created(tmp_path)
    listed, status = _route("list", {}, state, evidence)
    resumed, resume_status = _route("resume", {
        "journey_ref": ack["journey_ref"], "lens": "Verify"}, state, evidence)
    hidden, hidden_status = _route("resume", {
        "journey_ref": ack["journey_ref"], "lens": "Verify"}, state, evidence, OTHER)
    assert status == 200 and listed["journeys"][0]["journey_ref"] == ack["journey_ref"]
    assert resume_status == 200 and resumed["lens"] == "Verify"
    assert hidden_status == 404 and hidden["error"]["code"] == "JOURNEY_NOT_FOUND"
    assert OWNER not in json.dumps([listed, resumed])


def test_resume_rejects_unknown_lens_with_fixed_client_error(tmp_path):
    """An unsupported presentation lens must not surface as a storage failure."""
    state, evidence, ack = _created(tmp_path)
    result, status = _route("resume", {
        "journey_ref": ack["journey_ref"], "lens": "C:/private/secret",
    }, state, evidence)
    assert status == 422 and result["error"]["code"] == "INVALID_TRANSITION"
    assert "private" not in json.dumps(result)


def test_append_uses_only_allowlisted_command_types_and_server_time(tmp_path):
    """Raw operation types or caller timestamps must never become events."""
    state, evidence, created = _created(tmp_path)
    public = {"journey_ref": created["journey_ref"],
        "expected_event_head": created["event_head_sha256"],
        "client_request_id": "append-1", "command": {"type": "advance_stage"}}
    grant, _ = _grant("append", public, state, evidence)
    ack, status = _route("append", {**public, "grant_ref": grant}, state, evidence)
    bad, bad_status = grant_post("/api/grants/prepare/append", json.dumps({
        **public, "client_request_id": "bad",
        "command": {"type": "check_started"}}).encode(), owner_ref=OWNER,
        state_root=state, evidence_root=evidence, clock=lambda: NOW)
    projection, _ = _route("resume", {
        "journey_ref": created["journey_ref"], "lens": "Rescue"}, state, evidence)
    assert status == 200 and ack["event_head_sha256"] != created["event_head_sha256"]
    assert projection["stage"] == "decomposed"
    assert bad_status == 422 and bad["error"]["code"] == "INVALID_TRANSITION"


@pytest.mark.parametrize("nested", [
    {"claim_id": "claim-unsafe", "statement": "Forged", "depends_on": [],
     "does_not_prove": "verification", "verdict": "PASS",
     "receipt_refs": ["receipt.json"], "receipt_state": "MATCH"},
    {"claim_id": "claim-unsafe", "statement": "Forged", "depends_on": [],
     "does_not_prove": "verification", "provider": "remote"},
    {"claim_id": "claim-unsafe", "statement": "Forged", "depends_on": [],
     "does_not_prove": "verification", "error": "raw exception"},
    {"claim_id": "claim-unsafe", "statement": "Forged", "depends_on": [],
     "does_not_prove": "verification", "path": "C:/private/result"},
    {"claim_id": "claim-unsafe", "statement": "", "depends_on": [],
     "does_not_prove": "verification"},
    {"action_id": "next-1", "kind": "inspect", "description": "Inspect",
     "basis_refs": ["claim-1"], "lifecycle_event": "check_completed"},
])
def test_append_rejects_nested_authority_and_unknown_fields_before_proposal(
        tmp_path, nested):
    """Nested authority, unknown fields, and invalid facts never become authority."""
    state, evidence, created = _created(tmp_path)
    kind = "record_next_action" if "action_id" in nested else "record_claim"
    field = "next_action" if kind == "record_next_action" else "claim"
    before_proposals = list((state / "grant-proposals").rglob("*.json"))
    before_grants = list((state / "grants").rglob("*.json"))
    request = {"journey_ref": created["journey_ref"],
        "expected_event_head": created["event_head_sha256"],
        "client_request_id": "unsafe-append", "command": {
            "type": kind, field: nested}}
    result, status = grant_post("/api/grants/prepare/append",
        json.dumps(request).encode(), owner_ref=OWNER, state_root=state,
        evidence_root=evidence, clock=lambda: NOW)
    expected = ("UNSAFE_METADATA" if "path" in nested else
                "INVALID_METADATA" if nested.get("statement") == "" else "INVALID_TRANSITION")
    assert status == 422 and result["error"]["code"] == expected
    assert list((state / "grant-proposals").rglob("*.json")) == before_proposals
    assert list((state / "grants").rglob("*.json")) == before_grants


def test_record_claim_synthesizes_honest_null_verdict_and_receipt_state(tmp_path):
    """A client claim supplies facts; the server owns verdict and receipt state."""
    state, evidence, created = _created(tmp_path)
    claim = {"claim_id": "claim-1", "statement": "Candidate is correct",
        "depends_on": [], "does_not_prove": "candidate behavior"}
    request = {"journey_ref": created["journey_ref"],
        "expected_event_head": created["event_head_sha256"],
        "client_request_id": "claim-1", "command": {
            "type": "record_claim", "claim": claim}}
    grant, _ = _grant("append", request, state, evidence)
    ack, status = _route("append", {**request, "grant_ref": grant}, state, evidence)
    view, _ = _route("resume", {
        "journey_ref": ack["journey_ref"], "lens": "Verify"}, state, evidence)
    stored = view["claims"]["claim-1"]
    assert status == 200 and stored["verdict"] == "UNDECIDED"
    assert stored["receipt_state"] == "missing" and stored["receipt_refs"]


def test_export_route_publishes_packet_and_appends_export_event(tmp_path):
    """Export must be a service-owned packet plus CAS stage event, not a side write."""
    state, evidence = tmp_path / "state", tmp_path / "state" / "artifacts"
    evidence.mkdir(parents=True)
    store = JourneyStore(state)
    ack = store.create(MutationCommand(OWNER,
        "jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", None, "create-export",
        "intake", {"legacy_label": None, "goal": "Preserve evidence",
                   "intake": {}, "occurred_at": NOW}))
    for stage in ("decomposed", "preflight", "running", "concluded"):
        payload = {"conclusion": {"summary": "bounded"}} if stage == "concluded" else {}
        ack = store.append(MutationCommand(OWNER, ack.journey_ref,
            ack.event_head_sha256, f"stage-{stage}", stage,
            {"occurred_at": NOW, "payload": payload}))
    public = {"journey_ref": ack.journey_ref,
        "expected_event_head": ack.event_head_sha256,
        "client_request_id": "export-1", "packet_ref": "packets/out"}
    grant, _ = _grant("export", public, state, evidence)
    result, status = _route("export", {**public, "grant_ref": grant}, state, evidence)
    assert status == 200 and result["structural_verdict"] == "MATCH"
    assert result["source_event_head_sha256"] == public["expected_event_head"]
    assert (evidence / "packets" / "out" / "manifest.json").is_file()


def test_check_records_a_block_without_candidate_network_or_python_execution(
        tmp_path, monkeypatch):
    """A durable check request may block, but it cannot touch or execute Python."""
    state, evidence = tmp_path / "state", tmp_path / "state" / "artifacts"
    evidence.mkdir(parents=True)
    (evidence / "intake.json").write_text('{"summary":"bounded"}', encoding="utf-8")
    create = {"goal": "Check safely", "intake_ref": "intake.json",
              "client_request_id": "create-check"}
    grant, _ = _grant("create", create, state, evidence)
    ack, _ = _route("create", {**create, "grant_ref": grant}, state, evidence)
    advance = {"journey_ref": ack["journey_ref"],
        "expected_event_head": ack["event_head_sha256"],
        "client_request_id": "advance-check", "command": {"type": "advance_stage"}}
    grant, _ = _grant("append", advance, state, evidence)
    ack, _ = _route("append", {**advance, "grant_ref": grant}, state, evidence)
    claim = {"claim_id": "claim-1", "statement": "Candidate is correct",
        "depends_on": [], "does_not_prove": "candidate behavior"}
    record = {"journey_ref": ack["journey_ref"],
        "expected_event_head": ack["event_head_sha256"],
        "client_request_id": "claim-check",
        "command": {"type": "record_claim", "claim": claim}}
    grant, _ = _grant("append", record, state, evidence)
    ack, _ = _route("append", {**record, "grant_ref": grant}, state, evidence)
    (evidence / "context.json").write_text(json.dumps({
        "candidate_ref": "candidate.py", "task_id": "check-route"}), encoding="utf-8")
    check = {"journey_ref": ack["journey_ref"],
        "expected_event_head": ack["event_head_sha256"],
        "client_request_id": "check-1", "claim_id": "claim-1", "oracle_id": "code",
        "candidate_ref": "candidate.py", "context_ref": "context.json"}
    monkeypatch.setattr(socket, "create_connection", lambda *_a, **_k: pytest.fail("network"))
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_a, **_k: pytest.fail("network"))
    grant, proposed = _grant("check", check, state, evidence)
    result, status = _route("check", {**check, "grant_ref": grant}, state, evidence)
    assert status == 200 and result["state"] == "blocked"
    assert result["operation_ref"] == proposed["operation_ref"]
    assert not (evidence / "candidate.py").exists() and not (state / "receipts").exists()


def test_cancel_without_an_owned_process_is_fixed_unavailable(tmp_path):
    """No process handle means cancellation must not be labelled successful."""
    state, evidence, created = _created(tmp_path)
    operation = "op_0123456789abcdef0123456789abcdef"
    public = {"journey_ref": created["journey_ref"],
        "expected_event_head": created["event_head_sha256"],
        "client_request_id": "cancel-1", "operation_ref": operation}
    grant, _ = _grant("cancel", public, state, evidence)
    result, status = _route("cancel", {**public, "grant_ref": grant}, state, evidence)
    assert status == 409 and result["error"]["code"] == "CANCEL_UNAVAILABLE"


def test_routes_never_dispatch_provider_model_endpoint_or_network(tmp_path, monkeypatch):
    """Durable local custody must not turn into an execution or routing surface."""
    monkeypatch.setattr(socket, "create_connection", lambda *_a, **_k: pytest.fail("network"))
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_a, **_k: pytest.fail("network"))
    monkeypatch.setattr("harness.gateway.route_request", lambda *_a, **_k: pytest.fail("provider"))
    state, evidence, _ = _created(tmp_path)
    result, status = _route("list", {}, state, evidence)
    assert status == 200 and result["schema"] == "flywheel.evidence-journey-list/v2"


@pytest.mark.parametrize("path,module,function", [
    ("/api/journeys/list", "harness.journey_route", "journey_post"),
    ("/api/grants/approve-once", "harness.grant_route", "grant_post"),
])
def test_gateway_dispatches_private_routes_with_only_authenticated_owner(
        tmp_path, monkeypatch, path, module, function):
    """Gateway dispatch must pass private owner custody and admitted roots only."""
    handler = gateway._Handler.__new__(gateway._Handler)
    raw, captured = b"{}", []
    handler.path, handler.root = path, tmp_path / "evidence"
    handler.root.mkdir(); handler.flywheel_home = tmp_path / "home"
    handler.owner_ref = OWNER; handler.clock = lambda: NOW
    handler.rfile = io.BytesIO(raw)
    handler._content_length = lambda: len(raw)
    handler._json = lambda body, code=200: captured.append((body, code))
    def called(route, body, **kwargs):
        assert route == path and body == raw and kwargs["owner_ref"] == OWNER
        assert kwargs["state_root"] == handler.flywheel_home / "state"
        assert kwargs["evidence_root"] == handler.root
        return {"schema": "bounded"}, 200
    monkeypatch.setattr(f"{module}.{function}", called)
    handler._post()
    assert captured == [({"schema": "bounded"}, 200)]


def test_gateway_private_auth_failure_is_fixed_and_does_not_load_owner(tmp_path, monkeypatch):
    """Bearer refusal must precede stable owner file access."""
    handler = gateway._Handler.__new__(gateway._Handler)
    handler.path = "/api/journeys/list"; handler.command = "POST"
    handler.auth_token = "correct"; handler.allowed_hosts = gateway.DEFAULT_HOSTS
    handler.flywheel_home = tmp_path; handler.headers = {
        "Host": "localhost", "Authorization": "Bearer wrong",
        "Content-Type": "application/json"}
    handler.wfile = io.BytesIO(); statuses = []
    handler.send_response = statuses.append
    handler.send_header = lambda *_: None; handler.end_headers = lambda: None
    loads = []
    monkeypatch.setattr(gateway, "_auth_owner",
                        lambda *_a, **_k: loads.append(True) or (None, "bad_token"),
                        raising=False)
    assert handler._authorized() is False
    result = json.loads(handler.wfile.getvalue())
    assert statuses == [401] and result["error"]["code"] == "AUTH_REQUIRED"
    assert loads == [True]
