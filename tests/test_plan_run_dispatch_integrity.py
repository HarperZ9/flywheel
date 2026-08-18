from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from harness.evidence_json import canonical_sha256
from harness.gateway_grant_route import gateway_grant_post
from harness.journey_store import JourneyStore, MutationCommand
from harness.operation_grants import GrantStore
from harness.plan_run_contract import build_plan_run_result, verify_plan_result
from harness.plan_run_route import plan_post, plan_run_ref_for
from harness.plan_run_store import (
    PlanRunContractError,
    PlanRunStoreError,
    commit_plan_result,
    load_plan_prp,
    load_plan_result,
    seal_plan_prp,
)
from harness.workflows import WORKFLOWS, recompute_chain
from harness.profiles import PROFILES


NOW = "2026-08-15T12:00:00Z"
OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "a" * 32
FIXTURE = Path(__file__).parent / "fixtures" / "plan_run_contract_v1.json"


def _post(path, value, state, root, **options):
    resolve = options.pop("resolve_root", lambda _requested, _default: (root, None))
    return plan_post(
        path, json.dumps(value, separators=(",", ":")).encode(),
        owner_ref=OWNER, state_root=state, default_root=root,
        run_root=state / "runs", clock=lambda: NOW, resolve_root=resolve,
        **options,
    )


def _journey(state):
    return JourneyStore(state).create(MutationCommand(
        OWNER, JOURNEY, None, "create-1", "intake",
        {"legacy_label": None, "goal": "Bound plan", "intake": {},
         "occurred_at": NOW},
    ))


def _forge(state, root):
    result, status = _post("/api/plan/forge", {
        "goal": "implement sort that passes tests",
        "context": "A registered project is selected.",
    }, state, root)
    assert status == 200
    return result


def _operation(binding, root):
    return {
        "workflow": "code-change", "profile": "code", "root": str(root),
        "endpoint": "local", "allow_write": False, "allow_exec": False,
        "binding": binding, "data_refs": [], "credential_refs": [],
    }


def _prepare_approved(state, root):
    _journey(state)
    binding = _forge(state, root)
    head = JourneyStore(state).load(OWNER, JOURNEY)["event_head_sha256"]
    body = {"schema": "flywheel.gateway-operation/v1",
        "journey_ref": JOURNEY, "expected_event_head": head,
        "client_request_id": "request-1", "operation": _operation(binding, root)}
    proposal, status = gateway_grant_post(
        "/api/gateway-grants/prepare/plan.run", json.dumps(body).encode(),
        owner_ref=OWNER, state_root=state, clock=lambda: NOW,
    )
    assert status == 200
    approval, status = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": proposal["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=state, clock=lambda: NOW,
    )
    assert status == 200
    final = {"schema": "flywheel.gateway-operation/v1",
        "journey_ref": JOURNEY,
        "expected_event_head": proposal["expected_event_head"],
        "client_request_id": proposal["client_request_id"],
        "grant_ref": approval["grant_ref"], **_operation(binding, root)}
    return binding, final


def _workflow(workflow, endpoint, goal, *, steps=None, status="completed"):
    value = {"schema": "flywheel.workflow-run/v1", "workflow": workflow,
        "endpoint": endpoint, "goal_excerpt": goal[:200],
        "started": "2026-08-15T12:00:00", "steps": steps or [],
        "status": status}
    value["chain_hash"] = recompute_chain(value)
    return value


def _countersign(value):
    return {"kind": "workflow-run", "workflow": value["workflow"],
        "endpoint": value["endpoint"], "status": value["status"],
        "chain_hash": value["chain_hash"], "n_steps": len(value["steps"]),
        "stored": "ent_accepted", "store_chain_hash": "b" * 64}


def _after_consume(monkeypatch, callback):
    original = GrantStore.consume
    def consume(store, *args, **kwargs):
        result = original(store, *args, **kwargs)
        callback()
        return result
    monkeypatch.setattr(GrantStore, "consume", consume)


def _receipt_inputs(binding):
    return dict(workflow="code-change", endpoint="local",
        plan_run_ref="plr_" + "a" * 32, binding=binding,
        journey_ref=JOURNEY, expected_event_head="b" * 64,
        client_request_id="request-1", operation_sha256="c" * 64,
        arguments_sha256="d" * 64, authorization_sha256="e" * 64,
        grant_ref_sha256="f" * 64, execution_plan_sha256="1" * 64,
        workflow_sha256="2" * 64, profile_sha256="3" * 64,
        effective_system_sha256="4" * 64)


@pytest.mark.parametrize("target", [
    "first", "middle", "last", "order", "profile-system", "profile-list",
])
def test_post_consume_registry_mutation_cannot_change_dispatch(
        tmp_path, monkeypatch, target):
    _, final = _prepare_approved(tmp_path, tmp_path)
    prompts = []
    def agent(goal, _endpoint, **_kwargs):
        prompts.append(goal)
        return {"final": "done", "verified": True,
                "integrity": {"clean": True}}
    monkeypatch.setattr("harness.workflows.run_router_agent", agent)
    intact = deepcopy(WORKFLOWS["code-change"])
    intact_profile = deepcopy(PROFILES["code"])
    changed, profile = deepcopy(intact), deepcopy(intact_profile)
    if target in {"first", "middle"}:
        changed["steps"][("first", "middle").index(target)]["goal"] = (
            "MUTATED WORKFLOW {goal}")
    elif target == "last": changed["steps"][-1]["name"] = "mutated-last"
    elif target == "order": changed["steps"].reverse()
    elif target == "profile-system": profile["system"] = "MUTATED PROFILE"
    else: profile["planning"].reverse()
    monkeypatch.setitem(WORKFLOWS, "code-change", changed)
    monkeypatch.setitem(PROFILES, "code", profile)
    blocked, blocked_status = _post("/api/plan/run", final, tmp_path, tmp_path,
                                    countersign=_countersign)
    assert blocked_status == 403 and blocked["error"]["code"] == "PERMISSION_DENIED"
    assert prompts == [] and not list((tmp_path / "plan-runs").rglob("*.json"))
    monkeypatch.setitem(WORKFLOWS, "code-change", intact)
    monkeypatch.setitem(PROFILES, "code", intact_profile)
    def mutate():
        monkeypatch.setitem(WORKFLOWS, "code-change", changed)
        monkeypatch.setitem(PROFILES, "code", profile)
    _after_consume(monkeypatch, mutate)
    result, status = _post("/api/plan/run", final, tmp_path, tmp_path,
                           countersign=_countersign)
    assert status == 200 and result["workflow_run"]["workflow"] == "code-change"
    assert [step["name"] for step in result["workflow_run"]["steps"]] == (
        ["plan", "apply", "verify"])
    assert prompts and all("MUTATED" not in prompt for prompt in prompts)


@pytest.mark.parametrize("target", ["goal", "prompt", "gates"])
def test_post_consume_prp_accessor_mutation_cannot_change_dispatch(
        tmp_path, monkeypatch, target):
    binding, final = _prepare_approved(tmp_path, tmp_path)
    import harness.plan_run_store as store
    original, captured = store.verify_plan_run, []
    def capture(*args, **kwargs):
        verified = original(*args, **kwargs)
        captured.append(verified)
        return verified
    monkeypatch.setattr(store, "verify_plan_run", capture)
    def mutate():
        for verified in captured:
            if target == "goal": verified.record.prp["goal"] = "MUTATED PRP"
            elif target == "prompt": verified.binding.to_dict()["prompt"] = "MUTATED PRP"
            else: verified.binding.gates.clear()
    _after_consume(monkeypatch, mutate)
    calls = []
    def runner(workflow, goal, endpoint, **_kwargs):
        calls.append((goal, _kwargs["system"]))
        return _workflow(workflow, endpoint, goal)
    monkeypatch.setattr("harness.plan_run_route.run_workflow", runner)
    result, status = _post("/api/plan/run", final, tmp_path, tmp_path,
                           countersign=_countersign)
    assert status == 200 and result["receipt"]["binding"] == binding
    assert calls[0][0] == binding["prp"]["goal"]
    assert calls[0][1].startswith(binding["prompt"])


def test_outer_rehash_cannot_hide_stale_nested_workflow_chain():
    binding = json.loads(FIXTURE.read_text(encoding="utf-8"))["binding"]
    workflow = _workflow("code-change", "local", "goal", steps=[{
        "name": "plan", "kind": "agent", "status": "DONE",
        "excerpt": "original"}])
    workflow["run_countersign"] = _countersign(workflow)
    result = build_plan_run_result(
        workflow_run=workflow, **_receipt_inputs(binding))
    result["workflow_run"]["steps"][0]["excerpt"] = "forged"
    receipt = result["receipt"]
    receipt["workflow_run_sha256"] = canonical_sha256(result["workflow_run"])
    receipt["receipt_sha256"] = canonical_sha256({
        key: value for key, value in receipt.items() if key != "receipt_sha256"})
    result["result_sha256"] = canonical_sha256({
        key: value for key, value in result.items() if key != "result_sha256"})
    assert verify_plan_result(result)["verdict"] == "DRIFT"


@pytest.mark.parametrize("field,value", [
    ("workflow", "research-brief"), ("endpoint", "remote-other"),
])
def test_runner_identity_mismatch_fails_before_countersign_and_commit(
        tmp_path, monkeypatch, field, value):
    _, final = _prepare_approved(tmp_path, tmp_path)
    runs, signs = [], []
    def runner(workflow, goal, endpoint, **_kwargs):
        runs.append(1)
        identity = {"workflow": workflow, "endpoint": endpoint}
        identity[field] = value
        return _workflow(identity["workflow"], identity["endpoint"], goal)
    def countersign(doc):
        signs.append(1)
        return _countersign(doc)
    monkeypatch.setattr("harness.plan_run_route.run_workflow", runner)
    result, status = _post("/api/plan/run", final, tmp_path, tmp_path,
                           countersign=countersign)
    assert status == 502 and result["error"]["code"] == "EXTERNAL_ACTION_FAILED"
    assert runs == [1] and signs == []
    assert not list((tmp_path / "plan-runs" / OWNER).glob("*.json"))


def test_forge_record_selector_rejects_swapped_intact_record(tmp_path):
    prp = json.loads(FIXTURE.read_text(encoding="utf-8"))["binding"]["prp"]
    first = seal_plan_prp(prp, owner_ref=OWNER, state_root=tmp_path,
                          clock=lambda: NOW)
    other = deepcopy(prp)
    other["goal"] = "Implement a different stable sorting rule."
    other["prompt"] += "\nDifferent goal."
    second = seal_plan_prp(other, owner_ref=OWNER, state_root=tmp_path,
                           clock=lambda: NOW)
    owner = tmp_path / "plan-forge" / OWNER
    first_path = owner / f"{canonical_sha256(first.prp_id)}.json"
    second_path = owner / f"{canonical_sha256(second.prp_id)}.json"
    first_bytes, second_bytes = first_path.read_bytes(), second_path.read_bytes()
    first_path.write_bytes(second_bytes)
    second_path.write_bytes(first_bytes)
    with pytest.raises(PlanRunContractError) as failure:
        load_plan_prp(first.prp_id, owner_ref=OWNER, state_root=tmp_path)
    assert failure.value.code == "PLAN_BINDING_DRIFT"


def test_result_selector_rejects_swapped_intact_result(tmp_path):
    match = lambda _value: {"verdict": "MATCH"}
    first = {"schema": "fixture", "plan_run_ref": "plr_" + "a" * 32}
    second = {"schema": "fixture", "plan_run_ref": "plr_" + "b" * 32}
    commit_plan_result(first, owner_ref=OWNER, state_root=tmp_path, verifier=match)
    commit_plan_result(second, owner_ref=OWNER, state_root=tmp_path, verifier=match)
    owner = tmp_path / "plan-runs" / OWNER
    first_path = owner / f"{canonical_sha256(first['plan_run_ref'])}.json"
    second_path = owner / f"{canonical_sha256(second['plan_run_ref'])}.json"
    first_bytes, second_bytes = first_path.read_bytes(), second_path.read_bytes()
    first_path.write_bytes(second_bytes)
    second_path.write_bytes(first_bytes)
    with pytest.raises(PlanRunStoreError) as failure:
        load_plan_result(first["plan_run_ref"], owner_ref=OWNER,
                         state_root=tmp_path, verifier=match)
    assert failure.value.code == "STORE_COMMIT_FAILED"


def test_stored_v1_blocks_before_consume_or_dispatch_and_remains(tmp_path,
                                                                 monkeypatch):
    _, final = _prepare_approved(tmp_path, tmp_path)
    ref = plan_run_ref_for(OWNER, JOURNEY, "request-1")
    legacy = {"schema": "flywheel.plan-run-result/v1", "plan_run_ref": ref,
        "receipt": {}, "workflow_run": {}, "result_sha256": "a" * 64}
    commit_plan_result(legacy, owner_ref=OWNER, state_root=tmp_path,
                       verifier=lambda _value: {"verdict": "MATCH"})
    path = (tmp_path / "plan-runs" / OWNER /
            f"{canonical_sha256(ref)}.json")
    before, consumes, dispatches = path.read_bytes(), [], []
    original = GrantStore.consume
    def consume(store, *args, **kwargs):
        consumes.append(1)
        return original(store, *args, **kwargs)
    monkeypatch.setattr(GrantStore, "consume", consume)
    monkeypatch.setattr("harness.plan_run_route.run_workflow",
                        lambda *_args, **_kwargs: dispatches.append(1))
    result, status = _post("/api/plan/run", final, tmp_path, tmp_path,
                           countersign=_countersign)
    assert status == 500 and result["error"]["code"] == "STORE_COMMIT_FAILED"
    assert consumes == dispatches == [] and path.read_bytes() == before
