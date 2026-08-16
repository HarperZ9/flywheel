"""Closed, no-float contracts for one forged Plan run."""
from __future__ import annotations

import hashlib
import re

from .evidence_json import canonical_sha256
from .plan_run_snapshot import (
    ForgeRecord, FrozenJsonSnapshot, PlanRunBinding, PlanRunSnapshotError,
    VerifiedPlanRun, freeze_json, thaw_json,
)
from .plan_workflow_contract import (
    PlanWorkflowContractError, validate_plan_workflow_run,
)

PRP_SCHEMA = "flywheel.prp/v2"
BINDING_SCHEMA = "flywheel.plan-run-binding/v1"
FORGE_SCHEMA = "flywheel.forge-record/v2"
RECEIPT_SCHEMA = "flywheel.plan-run-receipt/v2"
RESULT_SCHEMA = "flywheel.plan-run-result/v2"
PRP_REF = re.compile(r"fpr_[0-9a-f]{32}\Z")
PLAN_RUN_REF = re.compile(r"plr_[0-9a-f]{32}\Z")
JOURNEY_REF = re.compile(r"jrn_[0-9a-f]{32}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
TASK_TYPES = frozenset(("code", "extraction", "transform", "analysis",
                        "research", "writing", "qa", "general"))
PLAN_LIMITATIONS = (
    "forged gates ran or passed", "workflow output is correct",
    "provider billing or side effects", "general execution containment",
    "off-host authenticity or signed provenance",
    "crash coverage inside the post-dispatch/pre-commit window",
    "Plan Stop or cancellation", "P3-T6 receipt inclusion",
    "installed upgrade or downgrade safety",
)
_PRP_FIELDS = {"schema", "goal", "task_type", "intent_sha256",
    "architecture_sha256", "confidence", "external_gate_ratio",
    "gate_counts", "well_posed", "validation_gates", "prompt"}
_BINDING_FIELDS = {"schema", "prp_id", "prp", "prp_sha256", "prompt",
    "prompt_sha256", "gates", "gates_sha256", "seal_sha256",
    "binding_sha256"}
_RECEIPT_FIELDS = {"schema", "plan_run_ref", "binding", "journey_ref",
    "expected_event_head", "client_request_id", "operation_sha256",
    "arguments_sha256", "authorization_sha256", "grant_ref_sha256",
    "execution_plan_sha256", "workflow", "endpoint", "workflow_sha256",
    "profile_sha256", "effective_system_sha256", "workflow_run_sha256",
    "workflow_status", "denominator", "does_not_prove", "receipt_sha256"}


class PlanRunContractError(RuntimeError):
    """One fixed contract failure, safe to expose by code only."""

    def __init__(self, code: str = "INVALID_REQUEST") -> None:
        self.code = code
        super().__init__(code)


def _freeze(value: object, *, max_bytes: int | None = None
            ) -> tuple[FrozenJsonSnapshot, dict]:
    try:
        snapshot = freeze_json(value, max_bytes=max_bytes)
        return snapshot, thaw_json(snapshot)
    except PlanRunSnapshotError:
        raise PlanRunContractError() from None


def canonical_plan_bytes(value: object, *, max_bytes: int | None = None) -> bytes:
    """Canonical JSON after the shared depth/node/no-float admission."""
    return _freeze(value, max_bytes=max_bytes)[0].canonical


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "strict")).hexdigest()


def _valid_sha(value: object, *, empty: bool = False) -> bool:
    return type(value) is str and (bool(SHA256.fullmatch(value))
                                   or empty and value == "")


def validate_prp(value: object) -> dict:
    _, prp = _freeze(value)
    if set(prp) != _PRP_FIELDS:
        raise PlanRunContractError()
    goal, prompt = prp.get("goal"), prp.get("prompt")
    if (prp.get("schema") != PRP_SCHEMA
            or prp.get("task_type") not in TASK_TYPES
            or type(goal) is not str or goal != goal.strip() or not goal
            or len(goal.encode("utf-8", "strict")) > 16384
            or type(prompt) is not str or not prompt
            or len(prompt.encode("utf-8", "strict")) > 65536
            or type(prp.get("confidence")) is not int
            or not 1 <= prp["confidence"] <= 10
            or type(prp.get("well_posed")) is not bool
            or not _valid_sha(prp.get("intent_sha256"), empty=True)
            or not _valid_sha(prp.get("architecture_sha256"), empty=True)):
        raise PlanRunContractError()
    _validate_gates(prp.get("validation_gates"), prp.get("gate_counts"),
                    prp.get("external_gate_ratio"))
    return prp


def _validate_gates(gates: object, counts: object, ratio: object) -> None:
    if type(gates) is not list or not 1 <= len(gates) <= 64:
        raise PlanRunContractError()
    seen = set()
    for gate in gates:
        if (type(gate) is not dict or set(gate) != {"check", "externally_checkable"}
                or type(gate.get("check")) is not str
                or not 1 <= len(gate["check"].encode("utf-8", "strict")) <= 4096
                or type(gate.get("externally_checkable")) is not bool):
            raise PlanRunContractError()
        key = gate["check"], gate["externally_checkable"]
        if key in seen:
            raise PlanRunContractError()
        seen.add(key)
    checkable = sum(gate["externally_checkable"] for gate in gates)
    if (type(counts) is not dict or set(counts) != {"checkable", "total"}
            or type(counts.get("checkable")) is not int
            or type(counts.get("total")) is not int
            or counts != {"checkable": checkable, "total": len(gates)}):
        raise PlanRunContractError()
    milli = (1000 * checkable + len(gates) // 2) // len(gates)
    if ratio != f"{milli // 1000}.{milli % 1000:03d}":
        raise PlanRunContractError()


def parse_plan_run_binding(value: object) -> PlanRunBinding:
    snapshot, binding = _freeze(value, max_bytes=524288)
    if set(binding) != _BINDING_FIELDS:
        raise PlanRunContractError()
    prp = validate_prp(binding.get("prp"))
    gates = prp["validation_gates"]
    unsigned = {key: item for key, item in binding.items()
                if key != "binding_sha256"}
    prp_id = binding.get("prp_id", "")
    if type(prp_id) is str and re.fullmatch(r"[0-9a-f]{16}", prp_id):
        raise PlanRunContractError("PLAN_BINDING_DRIFT")
    if (binding.get("schema") != BINDING_SCHEMA
            or type(prp_id) is not str or PRP_REF.fullmatch(prp_id) is None
            or binding.get("prompt") != prp["prompt"]
            or binding.get("gates") != gates
            or binding.get("prp_sha256") != canonical_sha256(prp)
            or binding.get("prompt_sha256") != _sha_text(prp["prompt"])
            or binding.get("gates_sha256") != canonical_sha256(gates)
            or not _valid_sha(binding.get("seal_sha256"))
            or binding.get("binding_sha256") != canonical_sha256(unsigned)):
        raise PlanRunContractError()
    return PlanRunBinding(snapshot, prp_id, binding["prp_sha256"],
        binding["prompt_sha256"], binding["gates_sha256"],
        binding["seal_sha256"], binding["binding_sha256"])


def build_plan_run_result(*, workflow_run: dict, workflow: str, endpoint: str,
        plan_run_ref: str, binding: dict | PlanRunBinding, journey_ref: str,
        expected_event_head: str, client_request_id: str,
        operation_sha256: str, arguments_sha256: str,
        authorization_sha256: str, grant_ref_sha256: str,
        execution_plan_sha256: str, workflow_sha256: str,
        profile_sha256: str, effective_system_sha256: str) -> dict:
    parsed = (binding if isinstance(binding, PlanRunBinding)
              else parse_plan_run_binding(binding))
    try:
        run = validate_plan_workflow_run(
            workflow_run, workflow=workflow, endpoint=endpoint,
            require_countersign=True)
    except PlanWorkflowContractError:
        raise PlanRunContractError() from None
    counts = parsed.prp["gate_counts"]
    receipt = {"schema": RECEIPT_SCHEMA, "plan_run_ref": plan_run_ref,
        "binding": parsed.to_dict(), "journey_ref": journey_ref,
        "expected_event_head": expected_event_head,
        "client_request_id": client_request_id,
        "operation_sha256": operation_sha256,
        "arguments_sha256": arguments_sha256,
        "authorization_sha256": authorization_sha256,
        "grant_ref_sha256": grant_ref_sha256,
        "execution_plan_sha256": execution_plan_sha256,
        "workflow": workflow, "endpoint": endpoint,
        "workflow_sha256": workflow_sha256, "profile_sha256": profile_sha256,
        "effective_system_sha256": effective_system_sha256,
        "workflow_run_sha256": canonical_sha256(run),
        "workflow_status": run["status"],
        "denominator": {"forged_gates": counts["total"],
            "checkable_gates": counts["checkable"],
            "forged_gates_executed": 0,
            "workflow_steps_recorded": len(run["steps"])},
        "does_not_prove": list(PLAN_LIMITATIONS)}
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    result = {"schema": RESULT_SCHEMA, "plan_run_ref": plan_run_ref,
              "receipt": receipt, "workflow_run": run}
    result["result_sha256"] = canonical_sha256(result)
    if verify_plan_result(result)["verdict"] != "MATCH":
        raise PlanRunContractError()
    return result


def _valid_receipt(value: object, workflow: dict, run_ref: str) -> bool:
    if type(value) is not dict or set(value) != _RECEIPT_FIELDS:
        return False
    try:
        binding = parse_plan_run_binding(value.get("binding"))
        run = validate_plan_workflow_run(workflow,
            workflow=value.get("workflow"), endpoint=value.get("endpoint"),
            require_countersign=True)
    except (PlanRunContractError, PlanWorkflowContractError):
        return False
    denominator, counts = value.get("denominator"), binding.prp["gate_counts"]
    plain = {"schema", "plan_run_ref", "binding", "journey_ref",
        "client_request_id", "workflow", "endpoint", "workflow_status",
        "denominator", "does_not_prove", "receipt_sha256"}
    return (value.get("schema") == RECEIPT_SCHEMA
        and value.get("plan_run_ref") == run_ref
        and JOURNEY_REF.fullmatch(value.get("journey_ref", "")) is not None
        and REQUEST_ID.fullmatch(value.get("client_request_id", "")) is not None
        and all(_valid_sha(value.get(name)) for name in _RECEIPT_FIELDS - plain)
        and value.get("workflow_run_sha256") == canonical_sha256(run)
        and value.get("workflow_status") == run["status"]
        and type(denominator) is dict
        and all(type(item) is int and item >= 0 for item in denominator.values())
        and denominator == {"forged_gates": counts["total"],
            "checkable_gates": counts["checkable"],
            "forged_gates_executed": 0,
            "workflow_steps_recorded": len(run["steps"])}
        and value.get("does_not_prove") == list(PLAN_LIMITATIONS)
        and value.get("receipt_sha256") == canonical_sha256({
            key: item for key, item in value.items() if key != "receipt_sha256"}))


def verify_plan_result(value: object) -> dict:
    """Re-derive every result and nested workflow digest."""
    try:
        _, result = _freeze(value)
        fields = {"schema", "plan_run_ref", "receipt", "workflow_run",
                  "result_sha256"}
        run_ref = result.get("plan_run_ref", "")
        workflow = result.get("workflow_run")
        match = (set(result) == fields
            and result.get("schema") == RESULT_SCHEMA
            and type(run_ref) is str and PLAN_RUN_REF.fullmatch(run_ref) is not None
            and type(workflow) is dict
            and _valid_receipt(result.get("receipt"), workflow, run_ref)
            and result.get("result_sha256") == canonical_sha256({
                key: item for key, item in result.items()
                if key != "result_sha256"}))
        return {"verdict": "MATCH" if match else "DRIFT"}
    except (AttributeError, PlanRunContractError, TypeError, ValueError):
        return {"verdict": "DRIFT"}
