from copy import deepcopy
import json
from pathlib import Path

import pytest

from harness.evidence_json import canonical_sha256
from harness.plan_run_contract import (
    PLAN_LIMITATIONS, PlanRunContractError, build_plan_run_result,
    parse_plan_run_binding, verify_plan_result,
)


FIXTURE = Path(__file__).parent / "fixtures" / "plan_run_contract_v1.json"


def _fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _workflow():
    return {
        "schema": "flywheel.workflow-run/v1", "workflow": "code-change",
        "endpoint": "local", "status": "completed", "steps": [],
        "chain_hash": "a" * 64,
        "run_countersign": {"kind": "workflow-run",
            "workflow": "code-change", "endpoint": "local",
            "status": "completed", "chain_hash": "a" * 64, "n_steps": 0,
            "stored": "ent_1", "store_chain_hash": "b" * 64},
    }


def _receipt_inputs(binding):
    return dict(
        plan_run_ref="plr_" + "a" * 32, binding=binding,
        journey_ref="jrn_" + "a" * 32, expected_event_head="b" * 64,
        client_request_id="request-1", operation_sha256="c" * 64,
        arguments_sha256="d" * 64, authorization_sha256="e" * 64,
        grant_ref_sha256="f" * 64, execution_plan_sha256="1" * 64,
        workflow_sha256="2" * 64, profile_sha256="3" * 64,
        effective_system_sha256="4" * 64,
    )


def test_shared_fixture_has_exact_cross_language_hashes_and_no_float():
    value = _fixture()
    parsed = parse_plan_run_binding(value["binding"])
    assert parsed.to_dict() == value["binding"]
    assert canonical_sha256(parsed.prp) == value["prp_sha256"]
    assert canonical_sha256(parsed.gates) == value["gates_sha256"]
    def contains_float(item):
        if type(item) is float:
            return True
        if type(item) is list:
            return any(contains_float(child) for child in item)
        if type(item) is dict:
            return any(contains_float(child) for child in item.values())
        return False
    assert contains_float(value) is False


@pytest.mark.parametrize("path,value", [
    (("schema",), "flywheel.prp/v1"), (("prp_id",), "fpr_" + "b" * 32),
    (("prp", "goal"), "Implement unstable sorting."),
    (("prp", "task_type"), "unknown"), (("prp", "confidence"), True),
    (("prp", "external_gate_ratio"), "0.999"),
    (("prp", "gate_counts", "checkable"), 1),
    (("prompt",), "changed"), (("gates", 0, "check"), "changed"),
    (("seal_sha256",), "0" * 64), (("binding_sha256",), "0" * 64),
])
def test_every_binding_and_prp_mutation_is_refused(path, value):
    binding = deepcopy(_fixture()["binding"])
    target = binding
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    with pytest.raises(PlanRunContractError):
        parse_plan_run_binding(binding)


def test_rehashed_wrong_binding_schema_is_refused():
    binding = deepcopy(_fixture()["binding"])
    binding["schema"] = "flywheel.plan-run-binding/v2"
    binding["binding_sha256"] = canonical_sha256({
        key: value for key, value in binding.items()
        if key != "binding_sha256"})
    with pytest.raises(PlanRunContractError):
        parse_plan_run_binding(binding)


@pytest.mark.parametrize("field,value", [
    ("confidence", 0), ("confidence", 11), ("confidence", 1.5),
    ("gate_counts", {"checkable": -1, "total": 2}),
    ("gate_counts", {"checkable": 3, "total": 2}),
    ("gate_counts", {"checkable": 1, "total": 65}),
])
def test_number_domain_and_counts_fail_closed(field, value):
    binding = deepcopy(_fixture()["binding"])
    binding["prp"][field] = value
    with pytest.raises(PlanRunContractError) as failure:
        parse_plan_run_binding(binding)
    assert failure.value.code == "INVALID_REQUEST"


def test_duplicate_gates_bounds_and_post_validation_trimming_are_refused():
    fixture = _fixture()["binding"]
    for mutate in (
        lambda b: b["prp"]["validation_gates"].append(
            deepcopy(b["prp"]["validation_gates"][0])),
        lambda b: b["prp"].__setitem__("goal", " goal "),
        lambda b: b["prp"].__setitem__("prompt", "x" * 65537),
        lambda b: b["prp"]["validation_gates"][0].__setitem__("check", ""),
    ):
        binding = deepcopy(fixture)
        mutate(binding)
        with pytest.raises(PlanRunContractError):
            parse_plan_run_binding(binding)


def test_result_verifier_rederives_every_nested_digest_and_has_no_authored_verdict():
    binding = _fixture()["binding"]
    result = build_plan_run_result(
        workflow_run=_workflow(), **_receipt_inputs(binding))
    assert verify_plan_result(result)["verdict"] == "MATCH"
    assert "verdict" not in result and result["receipt"]["does_not_prove"] == list(
        PLAN_LIMITATIONS)
    mutations = [("result_sha256", "0" * 64), ("plan_run_ref", "plr_" + "b" * 32)]
    for field, value in mutations:
        changed = deepcopy(result)
        changed[field] = value
        assert verify_plan_result(changed)["verdict"] == "DRIFT"
    nested = deepcopy(result)
    nested["workflow_run"]["status"] = "failed"
    assert verify_plan_result(nested)["verdict"] == "DRIFT"


def test_every_result_receipt_and_workflow_field_is_covered_by_a_digest():
    result = build_plan_run_result(
        workflow_run=_workflow(), **_receipt_inputs(_fixture()["binding"]))
    for container in ((), ("receipt",), ("workflow_run",)):
        target = result
        for part in container:
            target = target[part]
        for field in tuple(target):
            changed = deepcopy(result)
            changed_target = changed
            for part in container:
                changed_target = changed_target[part]
            changed_target[field] = None
            assert verify_plan_result(changed)["verdict"] == "DRIFT", (
                container, field)


def test_result_denominator_binds_forged_counts_without_claiming_execution():
    result = build_plan_run_result(
        workflow_run=_workflow(), **_receipt_inputs(_fixture()["binding"]))
    assert result["receipt"]["denominator"] == {
        "forged_gates": 2, "checkable_gates": 2,
        "forged_gates_executed": 0, "workflow_steps_recorded": 0,
    }


def test_rehashed_countersign_identity_drift_is_refused():
    result = build_plan_run_result(
        workflow_run=_workflow(), **_receipt_inputs(_fixture()["binding"]))
    result["workflow_run"]["run_countersign"]["status"] = "failed"
    result["receipt"]["workflow_run_sha256"] = canonical_sha256(
        result["workflow_run"])
    result["receipt"]["receipt_sha256"] = canonical_sha256({
        key: value for key, value in result["receipt"].items()
        if key != "receipt_sha256"})
    result["result_sha256"] = canonical_sha256({
        key: value for key, value in result.items() if key != "result_sha256"})
    assert verify_plan_result(result)["verdict"] == "DRIFT"


@pytest.mark.parametrize("target", ["denominator", "countersign"])
def test_bool_never_substitutes_for_receipt_integer(target):
    result = build_plan_run_result(
        workflow_run=_workflow(), **_receipt_inputs(_fixture()["binding"]))
    if target == "denominator":
        result["receipt"]["denominator"]["forged_gates_executed"] = False
    else:
        result["workflow_run"]["run_countersign"]["n_steps"] = False
        result["receipt"]["workflow_run_sha256"] = canonical_sha256(
            result["workflow_run"])
    result["receipt"]["receipt_sha256"] = canonical_sha256({
        key: value for key, value in result["receipt"].items()
        if key != "receipt_sha256"})
    result["result_sha256"] = canonical_sha256({
        key: value for key, value in result.items() if key != "result_sha256"})
    assert verify_plan_result(result)["verdict"] == "DRIFT"
