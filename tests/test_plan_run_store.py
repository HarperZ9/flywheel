from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from harness.evidence_json import canonical_bytes, canonical_sha256
from harness.plan_run_contract import PlanRunContractError
from harness.plan_run_store import (
    PlanRunStoreError, commit_plan_result, load_plan_prp, load_plan_result,
    seal_plan_prp, verify_plan_run,
)


FIXTURE = Path(__file__).parent / "fixtures" / "plan_run_contract_v1.json"
OWNER = "owner_" + "a" * 32
OTHER = "owner_" + "b" * 32
NOW = "2026-08-15T12:00:00Z"


def _prp():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["binding"]["prp"]


def _rehash(binding):
    prp, gates = binding["prp"], binding["prp"]["validation_gates"]
    checkable = sum(gate["externally_checkable"] for gate in gates)
    prp["gate_counts"] = {"checkable": checkable, "total": len(gates)}
    milli = (1000 * checkable + len(gates) // 2) // len(gates)
    prp["external_gate_ratio"] = f"{milli // 1000}.{milli % 1000:03d}"
    binding.update(prp_sha256=canonical_sha256(prp), prompt=prp["prompt"],
        prompt_sha256=hashlib.sha256(prp["prompt"].encode()).hexdigest(),
        gates=deepcopy(gates), gates_sha256=canonical_sha256(gates))
    binding["binding_sha256"] = canonical_sha256({
        key: value for key, value in binding.items() if key != "binding_sha256"})
    return binding


def test_create_and_exact_reforge_keep_first_seal_and_owner_private_path(tmp_path):
    first = seal_plan_prp(_prp(), owner_ref=OWNER, state_root=tmp_path,
                          clock=lambda: NOW)
    again = seal_plan_prp(_prp(), owner_ref=OWNER, state_root=tmp_path,
                          clock=lambda: "2026-08-15T13:00:00Z")
    assert first == again
    record = load_plan_prp(first.prp_id, owner_ref=OWNER, state_root=tmp_path)
    expected = (tmp_path / "plan-forge" / OWNER /
                f"{canonical_sha256(first.prp_id)}.json")
    assert expected.is_file() and record.created_at == NOW
    assert first.to_dict() == json.loads(
        FIXTURE.read_text(encoding="utf-8"))["binding"]


def test_owner_unknown_legacy_and_tampered_records_are_binding_drift(tmp_path):
    binding = seal_plan_prp(_prp(), owner_ref=OWNER, state_root=tmp_path,
                            clock=lambda: NOW)
    for owner, ref in ((OTHER, binding.prp_id), (OWNER, "fpr_" + "b" * 32),
                       (OWNER, "0123456789abcdef")):
        changed = binding.to_dict()
        changed["prp_id"] = ref
        changed["binding_sha256"] = canonical_sha256({
            key: value for key, value in changed.items()
            if key != "binding_sha256"})
        with pytest.raises(PlanRunContractError) as failure:
            verify_plan_run(changed, owner_ref=owner,
                            state_root=tmp_path)
        assert failure.value.code == "PLAN_BINDING_DRIFT"
    path = tmp_path / "plan-forge" / OWNER / f"{canonical_sha256(binding.prp_id)}.json"
    original = path.read_bytes()
    path.write_bytes(original.replace(b"Implement", b"XImplement", 1))
    with pytest.raises(PlanRunContractError):
        verify_plan_run(binding.to_dict(), owner_ref=OWNER, state_root=tmp_path)
    path.write_bytes(original)
    assert verify_plan_run(binding.to_dict(), owner_ref=OWNER,
                           state_root=tmp_path).binding == binding


def test_binding_mutation_never_uses_caller_authority(tmp_path):
    binding = seal_plan_prp(_prp(), owner_ref=OWNER, state_root=tmp_path,
                            clock=lambda: NOW).to_dict()
    for field in binding:
        changed = deepcopy(binding)
        changed[field] = [] if field in {"gates"} else "changed"
        with pytest.raises(PlanRunContractError):
            verify_plan_run(changed, owner_ref=OWNER, state_root=tmp_path)


@pytest.mark.parametrize("mutate", [
    lambda p: p.__setitem__("goal", "Implement another stable sorting rule."),
    lambda p: p.__setitem__("task_type", "analysis"),
    lambda p: p.__setitem__("intent_sha256", "b" * 64),
    lambda p: p.__setitem__("architecture_sha256", "c" * 64),
    lambda p: p.__setitem__("confidence", 9),
    lambda p: p.__setitem__("well_posed", not p["well_posed"]),
    lambda p: p.__setitem__("prompt", p["prompt"] + "\nChanged."),
    lambda p: p["validation_gates"][0].__setitem__("check", "changed"),
    lambda p: p["validation_gates"][-1].__setitem__(
        "externally_checkable", False),
    lambda p: p["validation_gates"].reverse(),
    lambda p: p["validation_gates"].append(
        {"check": "new check", "externally_checkable": False}),
    lambda p: p["validation_gates"].pop(),
])
def test_rehashed_well_formed_prp_and_gate_drift_never_gains_authority(
        tmp_path, mutate):
    binding = seal_plan_prp(_prp(), owner_ref=OWNER, state_root=tmp_path,
                            clock=lambda: NOW).to_dict()
    changed = deepcopy(binding)
    mutate(changed["prp"])
    changed = _rehash(changed)
    with pytest.raises(PlanRunContractError) as failure:
        verify_plan_run(changed, owner_ref=OWNER, state_root=tmp_path)
    assert failure.value.code == "PLAN_BINDING_DRIFT"


def test_result_commit_is_create_only_and_exact_replay_is_byte_equivalent(tmp_path):
    result = {"schema": "flywheel.plan-run-result/v1",
              "plan_run_ref": "plr_" + "a" * 32, "receipt": {},
              "workflow_run": {}, "result_sha256": "a" * 64}
    committed = commit_plan_result(
        result, owner_ref=OWNER, state_root=tmp_path,
        verifier=lambda _value: {"verdict": "MATCH"})
    loaded = load_plan_result(result["plan_run_ref"], owner_ref=OWNER,
                              state_root=tmp_path,
                              verifier=lambda _value: {"verdict": "MATCH"})
    assert loaded == result
    assert json.dumps(committed, separators=(",", ":"), ensure_ascii=False
                      ).encode() == canonical_bytes(result)
    changed = {**result, "result_sha256": "b" * 64}
    with pytest.raises(PlanRunStoreError) as mismatch:
        commit_plan_result(changed, owner_ref=OWNER, state_root=tmp_path,
                           verifier=lambda _value: {"verdict": "MATCH"})
    assert mismatch.value.code == "IDEMPOTENCY_MISMATCH"


def test_result_tamper_is_never_replayed(tmp_path):
    ref = "plr_" + "a" * 32
    result = {"schema": "flywheel.plan-run-result/v1", "plan_run_ref": ref,
              "receipt": {}, "workflow_run": {}, "result_sha256": "a" * 64}
    commit_plan_result(result, owner_ref=OWNER, state_root=tmp_path,
                       verifier=lambda _value: {"verdict": "MATCH"})
    path = tmp_path / "plan-runs" / OWNER / f"{canonical_sha256(ref)}.json"
    path.write_bytes(path.read_bytes().replace(b'"a', b'"b', 1))
    with pytest.raises(PlanRunStoreError):
        load_plan_result(ref, owner_ref=OWNER, state_root=tmp_path,
                         verifier=lambda _value: {"verdict": "DRIFT"})
