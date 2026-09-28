"""Gateway operation handles for v2 subagent child execution."""
from __future__ import annotations

import json
import time
from pathlib import Path

from .evidence_json import canonical_sha256
from .gateway_operation import (AuthorizedOperation, GatewayOperationError,
    canonicalize_operation)
from .gateway_operation_route import operation_ref_for
from .gateway_provider_adapter import ExecutionPlan
from .plan_run_snapshot import freeze_json
from .subagent_roles import RESULT_SCHEMA
from .subagent_gateway_contract import (ROUTE_EVIDENCE_SCHEMA, route_summary)

class GatewayChildHandle:
    def __init__(self, spec, parent_auth, service, process_factory,
                 state_root: Path):
        self.spec, self.parent, self.service = spec, parent_auth, service
        self.factory, self.state_root = process_factory, Path(state_root)
        self.operation_ref = spec["operation_ref"]; self._start()
    @property
    def pid(self):
        handle = self.service._handles.get((self.parent.owner_ref, self.operation_ref))
        return getattr(handle, "pid", None)
    def _authorized(self, expected_head):
        plan = ExecutionPlan(self.spec["execution_plan_sha256"],
            tuple(self.spec.get("required_slots", ())), (),
            agent_binding=freeze_json(self.spec["agent_binding"], max_bytes=32768))
        op = canonicalize_operation("agent.run", self.spec["operation"])
        return AuthorizedOperation(op.action, op.tool, op.destination,
            op.operation, op.operation_sha256, op.arguments_sha256, op.scopes,
            op.data_refs, op.credential_refs, self.parent.owner_ref,
            self.parent.journey_ref, expected_head, self.spec["client_request_id"],
            "gnt_" + canonical_sha256({"parent": self.parent.grant_ref,
                "child": self.spec["operation_sha256"]})[:32],
            self.parent.expires_at, plan)
    def _start(self):
        journey = self.service._journey(self.parent.owner_ref)
        for _ in range(8):
            head = journey.resume(self.parent.journey_ref)["event_head_sha256"]
            try:
                auth = self.service.credential_resolver(
                    self._authorized(head), self.service.state_root)
                self.snapshot = self.service.start(auth, self.factory)
                self._await_admitted_start()
                return
            except GatewayOperationError as exc:
                if exc.code != "HEAD_CONFLICT": raise
                time.sleep(0.01)
        raise GatewayOperationError("HEAD_CONFLICT")
    def _await_admitted_start(self) -> None:
        deadline = time.monotonic() + min(10.0,
            max(1.0, float(self.spec["route"]["budget"]["timeout_s"])))
        while time.monotonic() < deadline:
            snapshot = self.service.snapshot(
                self.parent.owner_ref, self.operation_ref)
            if snapshot.state != "queued":
                return
            time.sleep(0.01)
        raise GatewayOperationError("STORE_BUSY")

    def wait(self, timeout_s: float):
        terminal = self.service.wait_terminal(
            self.parent.owner_ref, self.operation_ref, timeout_s)
        result = self.service.result(self.parent.owner_ref,
            self.operation_ref)["result"]
        status = "completed" if terminal.state == "completed" else "failed"
        _write_result(Path(self.spec["workspace"]), self.spec, status,
            **operation_result_fields(self.spec, terminal.as_json(), result,
                                      self.service.state_root))
        return (0 if status == "completed" else 1), ""
    def stop(self) -> bool:
        handle = self.service._handles.get((self.parent.owner_ref, self.operation_ref))
        if handle is None or not getattr(handle, "signal_tree", None):
            return False
        ok = bool(handle.signal_tree())
        from .gateway_operation_process import WorkerOutcome
        outcome = handle.wait(1) or WorkerOutcome("cancelled", {"stopped": True})
        self.service._terminal(self.parent.owner_ref, self.operation_ref, outcome)
        return ok


def operation_result_fields(spec, gateway_operation, projection, state_root):
    records = []
    try:
        from .gateway_agent_trace import AgentTrace
        parent = spec["parent_authority"]
        records = AgentTrace(state_root, parent["owner_ref"],
            parent["journey_ref"], spec["operation_ref"]).read()
    except Exception:
        pass
    evidence = route_evidence(spec["agent_binding"],
        spec["operation_sha256"], records)
    return {"gateway_projection": projection, "gateway_operation": gateway_operation,
            "route_evidence": evidence,
            "agent_binding_sha256": spec["agent_binding_sha256"],
            "operation_sha256": spec["operation_sha256"],
            "operation_ref": spec["operation_ref"], "usage": evidence.get("usage")}


def _write_result(workspace: Path, spec: dict, status: str, **extra) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    payload = {"schema": RESULT_SCHEMA, "spec_sha256": spec["spec_sha256"],
        "role": spec.get("role", ""), "status": status, **extra}
    (workspace / "result.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def route_evidence(binding: dict, operation_sha256: str, records: list[dict]) -> dict:
    calls = []
    for rec in records:
        payload = rec.get("payload") if isinstance(rec, dict) else None
        meta = payload.get("meta") if isinstance(payload, dict) else None
        if isinstance(meta, dict) and meta.get("schema") == "flywheel.gateway-agent-model-call/v1":
            calls.append(meta)
    last = calls[-1] if calls else {}
    return {"schema": ROUTE_EVIDENCE_SCHEMA,
        **route_summary(binding, operation_sha256),
        "model_call_count": len(calls),
        "model_observed": last.get("model_observed"),
        "model_observation_basis": last.get("model_observation_basis", "unavailable"),
        "identity_status": last.get("identity_status", "unavailable"),
        "usage": last.get("usage"), "usage_reported": last.get("usage_reported"),
        "response_id": last.get("response_id"), "stop_reason": last.get("stop_reason"),
        "does_not_prove": ["MODEL_WEIGHTS_IDENTITY", "SEMANTIC_TRUTH"]}
