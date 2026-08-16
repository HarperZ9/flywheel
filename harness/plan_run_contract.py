"""Closed, no-float contracts for one forged Plan run."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import re

from .evidence_json import canonical_bytes, canonical_sha256

PRP_SCHEMA = "flywheel.prp/v2"
BINDING_SCHEMA = "flywheel.plan-run-binding/v1"
FORGE_SCHEMA = "flywheel.forge-record/v2"
RECEIPT_SCHEMA = "flywheel.plan-run-receipt/v1"
RESULT_SCHEMA = "flywheel.plan-run-result/v1"
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
    "execution_plan_sha256", "workflow_sha256", "profile_sha256",
    "effective_system_sha256", "workflow_run_sha256", "workflow_status",
    "denominator", "does_not_prove", "receipt_sha256"}
class PlanRunContractError(RuntimeError):
    """One fixed contract failure, safe to expose by code only."""

    def __init__(self, code: str = "INVALID_REQUEST") -> None:
        self.code = code
        super().__init__(code)
@dataclass(frozen=True)
class PlanRunBinding:
    prp_id: str
    prp: dict = field(repr=False)
    prp_sha256: str
    prompt: str = field(repr=False)
    prompt_sha256: str
    gates: list = field(repr=False)
    gates_sha256: str
    seal_sha256: str
    binding_sha256: str

    def to_dict(self) -> dict:
        return {"schema": BINDING_SCHEMA, "prp_id": self.prp_id,
                "prp": deepcopy(self.prp), "prp_sha256": self.prp_sha256,
                "prompt": self.prompt, "prompt_sha256": self.prompt_sha256,
                "gates": deepcopy(self.gates), "gates_sha256": self.gates_sha256,
                "seal_sha256": self.seal_sha256,
                "binding_sha256": self.binding_sha256}
@dataclass(frozen=True)
class ForgeRecord:
    owner_ref: str
    prp_id: str
    prp: dict = field(repr=False)
    prp_sha256: str
    prompt_sha256: str
    gates_sha256: str
    created_at: str
    seal_sha256: str

    def to_dict(self) -> dict:
        return {"schema": FORGE_SCHEMA, "owner_ref": self.owner_ref,
                "prp_id": self.prp_id, "prp": deepcopy(self.prp),
                "prp_sha256": self.prp_sha256,
                "prompt_sha256": self.prompt_sha256,
                "gates_sha256": self.gates_sha256,
                "created_at": self.created_at, "seal_sha256": self.seal_sha256}
@dataclass(frozen=True)
class VerifiedPlanRun:
    binding: PlanRunBinding = field(repr=False)
    record: ForgeRecord = field(repr=False)
def _snapshot(value: object, remaining: list[int], depth: int = 0):
    remaining[0] -= 1
    if remaining[0] < 0 or depth > 16:
        raise PlanRunContractError()
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is list:
        return [_snapshot(item, remaining, depth + 1) for item in value]
    if type(value) is dict and all(type(key) is str for key in value):
        return {key: _snapshot(item, remaining, depth + 1)
                for key, item in value.items()}
    raise PlanRunContractError()
def canonical_plan_bytes(value: object, *, max_bytes: int | None = None) -> bytes:
    """Canonical JSON after the shared depth/node/no-float admission."""
    try:
        encoded = canonical_bytes(_snapshot(value, [4096]))
    except PlanRunContractError:
        raise
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise PlanRunContractError() from None
    if max_bytes is not None and len(encoded) > max_bytes:
        raise PlanRunContractError()
    return encoded
def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
def _valid_sha(value: object, *, empty: bool = False) -> bool:
    return type(value) is str and (bool(SHA256.fullmatch(value))
                                   or empty and value == "")
def validate_prp(value: object) -> dict:
    prp = _snapshot(value, [4096])
    if type(prp) is not dict or set(prp) != _PRP_FIELDS:
        raise PlanRunContractError()
    goal, prompt, gates, counts = (prp.get("goal"), prp.get("prompt"),
                                    prp.get("validation_gates"),
                                    prp.get("gate_counts"))
    if (prp.get("schema") != PRP_SCHEMA or prp.get("task_type") not in TASK_TYPES
            or type(goal) is not str or goal != goal.strip() or not goal
            or len(goal.encode("utf-8")) > 16384
            or type(prompt) is not str or not prompt
            or len(prompt.encode("utf-8")) > 65536
            or type(prp.get("confidence")) is not int
            or not 1 <= prp["confidence"] <= 10
            or type(prp.get("well_posed")) is not bool
            or not _valid_sha(prp.get("intent_sha256"), empty=True)
            or not _valid_sha(prp.get("architecture_sha256"), empty=True)):
        raise PlanRunContractError()
    _validate_gates(gates, counts, prp.get("external_gate_ratio"))
    canonical_plan_bytes(prp)
    return prp
def _validate_gates(gates: object, counts: object, ratio: object) -> None:
    if type(gates) is not list or not 1 <= len(gates) <= 64:
        raise PlanRunContractError()
    seen = set()
    for gate in gates:
        if (type(gate) is not dict or set(gate) != {"check", "externally_checkable"}
                or type(gate.get("check")) is not str
                or not 1 <= len(gate["check"].encode("utf-8")) <= 4096
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
    binding = _snapshot(value, [4096])
    canonical_plan_bytes(binding, max_bytes=524288)
    if type(binding) is not dict or set(binding) != _BINDING_FIELDS:
        raise PlanRunContractError()
    prp = validate_prp(binding.get("prp"))
    gates = prp["validation_gates"]
    unsigned = {key: item for key, item in binding.items()
                if key != "binding_sha256"}
    prp_id = binding.get("prp_id", "")
    if (type(prp_id) is str and re.fullmatch(r"[0-9a-f]{16}", prp_id)
            is not None):
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
    return PlanRunBinding(binding["prp_id"], prp, binding["prp_sha256"],
        binding["prompt"], binding["prompt_sha256"], gates,
        binding["gates_sha256"], binding["seal_sha256"],
        binding["binding_sha256"])
def build_plan_run_result(*, workflow_run: dict, plan_run_ref: str,
        binding: dict | PlanRunBinding, journey_ref: str,
        expected_event_head: str, client_request_id: str,
        operation_sha256: str, arguments_sha256: str,
        authorization_sha256: str, grant_ref_sha256: str,
        execution_plan_sha256: str, workflow_sha256: str,
        profile_sha256: str, effective_system_sha256: str) -> dict:
    parsed = (binding if isinstance(binding, PlanRunBinding)
              else parse_plan_run_binding(binding))
    workflow = _snapshot(workflow_run, [4096])
    canonical_plan_bytes(workflow)
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
        "workflow_sha256": workflow_sha256, "profile_sha256": profile_sha256,
        "effective_system_sha256": effective_system_sha256,
        "workflow_run_sha256": canonical_sha256(workflow),
        "workflow_status": workflow.get("status", ""),
        "denominator": {"forged_gates": counts["total"],
            "checkable_gates": counts["checkable"],
            "forged_gates_executed": 0,
            "workflow_steps_recorded": len(workflow.get("steps", ()))},
        "does_not_prove": list(PLAN_LIMITATIONS)}
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    result = {"schema": RESULT_SCHEMA, "plan_run_ref": plan_run_ref,
              "receipt": receipt, "workflow_run": workflow}
    result["result_sha256"] = canonical_sha256(result)
    if verify_plan_result(result)["verdict"] != "MATCH":
        raise PlanRunContractError()
    return result
def _valid_receipt(value: object, workflow: dict, run_ref: str) -> bool:
    if type(value) is not dict or set(value) != _RECEIPT_FIELDS:
        return False
    try:
        binding = parse_plan_run_binding(value.get("binding"))
    except PlanRunContractError:
        return False
    denominator = value.get("denominator")
    counts = binding.prp["gate_counts"]
    countersign = workflow.get("run_countersign")
    identity = {"kind": "workflow-run", "workflow": workflow.get("workflow"),
        "endpoint": workflow.get("endpoint"), "status": workflow.get("status"),
        "chain_hash": workflow.get("chain_hash"),
        "n_steps": len(workflow.get("steps", ())) }
    digests = _RECEIPT_FIELDS - {"schema", "plan_run_ref", "binding",
        "journey_ref", "client_request_id", "workflow_status", "denominator",
        "does_not_prove", "receipt_sha256"}
    return (value.get("schema") == RECEIPT_SCHEMA
        and value.get("plan_run_ref") == run_ref
        and JOURNEY_REF.fullmatch(value.get("journey_ref", "")) is not None
        and REQUEST_ID.fullmatch(value.get("client_request_id", "")) is not None
        and workflow.get("schema") == "flywheel.workflow-run/v1"
        and type(workflow.get("workflow")) is str and bool(workflow["workflow"])
        and type(workflow.get("endpoint")) is str and bool(workflow["endpoint"])
        and _valid_sha(workflow.get("chain_hash"))
        and type(workflow.get("status")) is str
        and type(workflow.get("steps")) is list
        and type(countersign) is dict
        and set(countersign) == set(identity) | {"stored", "store_chain_hash"}
        and all(countersign.get(key) == item for key, item in identity.items())
        and type(countersign.get("n_steps")) is int
        and type(countersign.get("stored")) is str and bool(countersign["stored"])
        and _valid_sha(countersign.get("store_chain_hash"))
        and all(_valid_sha(value.get(name)) for name in digests)
        and value.get("workflow_run_sha256") == canonical_sha256(workflow)
        and value.get("workflow_status") == workflow.get("status")
        and type(denominator) is dict
        and all(type(item) is int and item >= 0 for item in denominator.values())
        and denominator == {"forged_gates": counts["total"],
            "checkable_gates": counts["checkable"],
            "forged_gates_executed": 0,
            "workflow_steps_recorded": len(workflow.get("steps", ())) }
        and value.get("does_not_prove") == list(PLAN_LIMITATIONS)
        and value.get("receipt_sha256") == canonical_sha256({
            key: item for key, item in value.items() if key != "receipt_sha256"}))


def verify_plan_result(value: object) -> dict:
    """Re-derive every result digest; never trust a caller verdict."""
    try:
        result = _snapshot(value, [4096])
        canonical_plan_bytes(result)
        fields = {"schema", "plan_run_ref", "receipt", "workflow_run",
                  "result_sha256"}
        run_ref, workflow = result.get("plan_run_ref", ""), result.get("workflow_run")
        match = (type(result) is dict and set(result) == fields
            and result.get("schema") == RESULT_SCHEMA
            and PLAN_RUN_REF.fullmatch(run_ref) is not None
            and type(workflow) is dict
            and _valid_receipt(result.get("receipt"), workflow, run_ref)
            and result.get("result_sha256") == canonical_sha256({
                key: item for key, item in result.items()
                if key != "result_sha256"}))
        return {"verdict": "MATCH" if match else "DRIFT"}
    except (AttributeError, PlanRunContractError, TypeError, ValueError):
        return {"verdict": "DRIFT"}
