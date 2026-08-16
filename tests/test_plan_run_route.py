from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json

import pytest

from harness.evidence_json import canonical_sha256
from harness.gateway_grant_route import gateway_grant_post
from harness.journey_store import JourneyStore, MutationCommand
from harness.plan_run_route import plan_post
from harness.workflows import recompute_chain


NOW = "2026-08-15T12:00:00Z"
OWNER = "owner_" + "a" * 32
OTHER = "owner_" + "b" * 32
JOURNEY = "jrn_" + "a" * 32


def _journey(state):
    return JourneyStore(state).create(MutationCommand(
        OWNER, JOURNEY, None, "create-1", "intake",
        {"legacy_label": None, "goal": "Bound plan", "intake": {},
         "occurred_at": NOW}))


def _post(path, value, state, root, **kw):
    resolve = kw.pop("resolve_root", lambda requested, _default: (root, None))
    return plan_post(
        path, json.dumps(value, separators=(",", ":")).encode(),
        owner_ref=kw.pop("owner_ref", OWNER), state_root=state,
        default_root=root, run_root=state / "runs", clock=lambda: NOW,
        resolve_root=resolve, **kw)


def _forge(state, root):
    result, status = _post("/api/plan/forge", {
        "goal": "implement sort that passes tests",
        "context": "A registered project is selected.",
        "intent_source": "users need stable sorting",
        "architecture_source": "use the existing sorting module",
    }, state, root)
    assert status == 200
    return result


def _operation(binding, root):
    return {
        "workflow": "code-change", "profile": "code", "root": str(root),
        "endpoint": "local", "allow_write": False, "allow_exec": False,
        "binding": binding, "data_refs": [], "credential_refs": [],
    }


def _prepare(state, binding, root, request="request-1"):
    head = JourneyStore(state).load(OWNER, JOURNEY)["event_head_sha256"]
    body = {"schema": "flywheel.gateway-operation/v1",
            "journey_ref": JOURNEY, "expected_event_head": head,
            "client_request_id": request,
            "operation": _operation(binding, root)}
    return gateway_grant_post(
        "/api/gateway-grants/prepare/plan.run", json.dumps(body).encode(),
        owner_ref=OWNER, state_root=state, clock=lambda: NOW)


def _approve(state, proposal):
    return gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": proposal["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=state, clock=lambda: NOW)


def _final(proposal, grant, binding, workspace, **changes):
    body = {"schema": "flywheel.gateway-operation/v1",
            "journey_ref": JOURNEY,
            "expected_event_head": proposal["expected_event_head"],
            "client_request_id": proposal["client_request_id"],
            "grant_ref": grant, **_operation(binding, workspace)}
    body.update(changes)
    return body


def _runner_spy(calls):
    def run(workflow, goal, endpoint, **kwargs):
        calls.append((workflow, goal, endpoint, kwargs))
        value = {"schema": "flywheel.workflow-run/v1", "workflow": workflow,
            "endpoint": endpoint, "goal_excerpt": goal[:200],
            "started": "2026-08-15T12:00:00", "status": "completed",
            "steps": []}
        value["chain_hash"] = recompute_chain(value)
        return value
    return run


def _countersign(doc):
    return {"kind": "workflow-run", "workflow": doc["workflow"],
            "endpoint": doc["endpoint"], "status": doc["status"],
            "chain_hash": doc["chain_hash"], "n_steps": len(doc["steps"]),
            "stored": "ent_accepted", "store_chain_hash": "b" * 64}


def test_authenticated_forge_is_owner_scoped_and_recheck_exposes_no_path(tmp_path):
    binding = _forge(tmp_path, tmp_path)
    recheck, status = _post("/api/plan/forge/recheck", {
        "prp_id": binding["prp_id"],
        "intent_source": "users need stable sorting",
        "architecture_source": "changed",
    }, tmp_path, tmp_path)
    assert status == 200 and recheck["arms"]["intent"]["moved"] is False
    assert recheck["arms"]["architecture"]["moved"] is True
    assert "seal_path" not in recheck and str(tmp_path) not in json.dumps(recheck)
    refused, code = _post("/api/plan/forge/recheck", {
        "prp_id": binding["prp_id"], "intent_source": "same",
    }, tmp_path, tmp_path, owner_ref=OTHER)
    assert code == 409 and refused["error"]["code"] == "PLAN_BINDING_DRIFT"


def test_prepare_drift_creates_no_proposal_or_grant(tmp_path):
    _journey(tmp_path)
    binding = _forge(tmp_path, tmp_path)
    changed = deepcopy(binding)
    changed["seal_sha256"] = "0" * 64
    changed["binding_sha256"] = canonical_sha256(
        {key: value for key, value in changed.items()
         if key != "binding_sha256"})
    result, status = _prepare(tmp_path, changed, tmp_path)
    assert status == 409 and result["error"] == {
        "code": "PLAN_BINDING_DRIFT",
        "message": "plan run does not match its forged contract"}
    assert not list((tmp_path / "gateway-grant-proposals").rglob("*.json"))
    assert not list((tmp_path / "grants").rglob("*.json"))


def test_one_consume_dispatch_commit_then_exact_replay(tmp_path, monkeypatch):
    _journey(tmp_path)
    binding = _forge(tmp_path, tmp_path)
    proposal, status = _prepare(tmp_path, binding, tmp_path)
    assert status == 200 and proposal["action"] == "plan.run"
    approval, status = _approve(tmp_path, proposal)
    assert status == 200
    calls = []
    monkeypatch.setattr("harness.plan_run_route.run_workflow", _runner_spy(calls))
    final = _final(proposal, approval["grant_ref"], binding, tmp_path)
    first, status = _post("/api/plan/run", final, tmp_path, tmp_path,
                          countersign=_countersign)
    replay, replay_status = _post("/api/plan/run", final, tmp_path, tmp_path,
                                  countersign=_countersign)
    assert (status, replay_status) == (200, 200) and replay == first
    assert len(calls) == 1
    sent = calls[0]
    assert sent[1] == binding["prp"]["goal"]
    assert sent[3]["system"].startswith(binding["prompt"] + "\n\n")
    assert sent[3]["system"].endswith(
        "do not claim success the checks do not show.")
    assert sent[3]["allow_mcp"] is False and sent[3]["authorized"] is True
    assert first["receipt"]["denominator"]["forged_gates_executed"] == 0
    forge_path = next((tmp_path / "plan-forge" / OWNER).glob("*.json"))
    forge_path.write_bytes(forge_path.read_bytes().replace(b"tests", b"tEsts", 1))
    replay, replay_status = _post("/api/plan/run", final, tmp_path, tmp_path,
                                  countersign=_countersign)
    assert replay_status == 200 and replay == first and len(calls) == 1


def test_tamper_before_final_does_not_burn_then_restore_succeeds(tmp_path, monkeypatch):
    _journey(tmp_path)
    binding = _forge(tmp_path, tmp_path)
    proposal, _ = _prepare(tmp_path, binding, tmp_path)
    approval, _ = _approve(tmp_path, proposal)
    path = next((tmp_path / "plan-forge" / OWNER).glob("*.json"))
    intact = path.read_bytes()
    path.write_bytes(intact.replace(b"tests", b"tEsts", 1))
    final = _final(proposal, approval["grant_ref"], binding, tmp_path)
    blocked, status = _post("/api/plan/run", final, tmp_path, tmp_path,
                            countersign=_countersign)
    assert status == 409 and blocked["error"]["code"] == "PLAN_BINDING_DRIFT"
    path.write_bytes(intact)
    calls = []
    monkeypatch.setattr("harness.plan_run_route.run_workflow", _runner_spy(calls))
    completed, status = _post("/api/plan/run", final, tmp_path, tmp_path,
                              countersign=_countersign)
    assert status == 200 and completed["schema"] == "flywheel.plan-run-result/v2"
    assert len(calls) == 1


def test_root_resolution_fault_is_fixed_preconsume_and_restore_succeeds(
        tmp_path, monkeypatch):
    _journey(tmp_path)
    binding = _forge(tmp_path, tmp_path)
    proposal, _ = _prepare(tmp_path, binding, tmp_path)
    approval, _ = _approve(tmp_path, proposal)
    final = _final(proposal, approval["grant_ref"], binding, tmp_path)
    def root_fault(*_args):
        raise OSError("PRIVATE_ROOT_MARKER")
    blocked, status = _post("/api/plan/run", final, tmp_path, tmp_path,
        resolve_root=root_fault, countersign=_countersign)
    assert status == 422 and blocked["error"]["code"] == "INVALID_REQUEST"
    assert "PRIVATE_ROOT_MARKER" not in repr(blocked)
    calls = []
    monkeypatch.setattr("harness.plan_run_route.run_workflow", _runner_spy(calls))
    completed, status = _post("/api/plan/run", final, tmp_path, tmp_path,
                              countersign=_countersign)
    assert status == 200 and completed["schema"] == "flywheel.plan-run-result/v2"
    assert len(calls) == 1


def test_two_concurrent_exact_finals_dispatch_and_commit_once(tmp_path, monkeypatch):
    _journey(tmp_path)
    binding = _forge(tmp_path, tmp_path)
    proposal, _ = _prepare(tmp_path, binding, tmp_path)
    approval, _ = _approve(tmp_path, proposal)
    calls = []
    monkeypatch.setattr("harness.plan_run_route.run_workflow", _runner_spy(calls))
    final = _final(proposal, approval["grant_ref"], binding, tmp_path)
    def dispatch(_index):
        return _post("/api/plan/run", final, tmp_path, tmp_path,
                     countersign=_countersign)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(dispatch, range(2)))
    assert [status for _, status in outcomes] == [200, 200]
    assert outcomes[0][0] == outcomes[1][0] and len(calls) == 1
    assert len(list((tmp_path / "plan-runs" / OWNER).glob("*.json"))) == 1


def test_workflow_failure_is_fixed_marker_free_and_burns_once(tmp_path, monkeypatch):
    _journey(tmp_path)
    binding = _forge(tmp_path, tmp_path)
    proposal, _ = _prepare(tmp_path, binding, tmp_path)
    approval, _ = _approve(tmp_path, proposal)
    calls = []
    def fail(*_args, **_kwargs):
        calls.append(1)
        raise RuntimeError("PRIVATE_WORKFLOW_MARKER")
    monkeypatch.setattr("harness.plan_run_route.run_workflow", fail)
    final = _final(proposal, approval["grant_ref"], binding, tmp_path)
    failed, status = _post("/api/plan/run", final, tmp_path, tmp_path,
                           countersign=_countersign)
    retry, retry_status = _post("/api/plan/run", final, tmp_path, tmp_path,
                                countersign=_countersign)
    assert status == 502 and failed["error"]["code"] == "EXTERNAL_ACTION_FAILED"
    assert "PRIVATE_WORKFLOW_MARKER" not in repr(failed)
    assert retry_status == 403 and len(calls) == 1


@pytest.mark.parametrize("field,value", [
    ("workflow", "research-brief"), ("profile", "work"),
    ("root", "changed"), ("endpoint", "remote"), ("allow_write", True),
    ("allow_exec", True), ("test_cmd", "pytest -q"),
    ("data_refs", ["data_changed"]),
    ("credential_refs", ["cred_" + "b" * 32]),
])
def test_every_final_operation_drift_is_preconsume(tmp_path, field, value):
    _journey(tmp_path)
    binding = _forge(tmp_path, tmp_path)
    proposal, _ = _prepare(tmp_path, binding, tmp_path)
    approval, _ = _approve(tmp_path, proposal)
    changed = _final(proposal, approval["grant_ref"], binding, tmp_path,
                     **{field: value})
    _, status = _post("/api/plan/run", changed, tmp_path, tmp_path,
                      countersign=_countersign)
    assert status in {403, 409, 422}


def test_same_request_changed_semantics_is_idempotency_mismatch(tmp_path, monkeypatch):
    _journey(tmp_path)
    binding = _forge(tmp_path, tmp_path)
    proposal, _ = _prepare(tmp_path, binding, tmp_path)
    approval, _ = _approve(tmp_path, proposal)
    monkeypatch.setattr("harness.plan_run_route.run_workflow", _runner_spy([]))
    final = _final(proposal, approval["grant_ref"], binding, tmp_path)
    assert _post("/api/plan/run", final, tmp_path, tmp_path,
                 countersign=_countersign)[1] == 200
    changed = {**final, "allow_write": True}
    result, status = _post("/api/plan/run", changed, tmp_path, tmp_path,
                           countersign=_countersign)
    assert status == 409 and result["error"]["code"] == "IDEMPOTENCY_MISMATCH"


def test_invalid_countersign_burns_once_and_never_commits(tmp_path, monkeypatch):
    _journey(tmp_path)
    binding = _forge(tmp_path, tmp_path)
    proposal, _ = _prepare(tmp_path, binding, tmp_path)
    approval, _ = _approve(tmp_path, proposal)
    calls = []
    monkeypatch.setattr("harness.plan_run_route.run_workflow", _runner_spy(calls))
    final = _final(proposal, approval["grant_ref"], binding, tmp_path)
    bad_sign = lambda _doc: {"stored": "ent_bad", "store_chain_hash": "z" * 64}
    result, status = _post("/api/plan/run", final, tmp_path, tmp_path,
                           countersign=bad_sign)
    retry, retry_status = _post("/api/plan/run", final, tmp_path, tmp_path,
                                countersign=_countersign)
    assert status == 500 and result["error"]["code"] == "STORE_COMMIT_FAILED"
    assert retry_status == 403
    assert retry["error"]["code"] in {"APPROVAL_EXPIRED", "PERMISSION_DENIED"}
    assert len(calls) == 1
    assert not list((tmp_path / "plan-runs" / OWNER).glob("*.json"))
