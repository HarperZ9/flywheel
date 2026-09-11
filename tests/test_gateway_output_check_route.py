from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

from harness.cross_harness_process import ProcessOutcome
from harness.gateway_custody import is_private
from harness.evidence_json import canonical_bytes
from harness.gateway_grant_route import gateway_grant_post
from harness.gateway_operation_process import (
    GatewayOperationProcessFactory,
    GatewayOutputCheckProcessFactory,
)
from harness.gateway_operation_route import operation_ref_for, route_gateway_operation
from harness.gateway_operations import GatewayOperations
from harness.journey_store import JourneyStore, MutationCommand


OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "a" * 32
NOW = "2026-09-10T12:00:00Z"


def test_output_check_route_is_private_and_factory_exposes_workspace_root(tmp_path):
    assert is_private("/api/output/check") is True
    factory = GatewayOperationProcessFactory(
        repo_root=tmp_path, run_root=tmp_path / "run",
        state_root=tmp_path / "state")
    assert factory.repo_root == tmp_path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_inputs(root: Path) -> dict:
    (root / "rows.json").write_text(json.dumps({"36700": 4169}),
                                    encoding="utf-8")
    contract = root / "contract.json"
    contract.write_text(json.dumps({
        "fields": [{"name": "tax", "authority": "TABLE", "source": "t"}],
        "authorities": {"t": {"kind": "table", "path": "rows.json",
                              "key_field": "taxable_income"}},
    }), encoding="utf-8")
    answer = root / "answer.json"
    answer.write_text(json.dumps({
        "taxable_income": {"value": 36700, "source": "return"},
        "tax": {"value": 4169, "source": "t"},
    }), encoding="utf-8")
    return {
        "contract": {"kind": "workspace-file", "path": "contract.json",
                     "sha256": _sha(contract)},
        "answer": {"kind": "workspace-file", "path": "answer.json",
                   "sha256": _sha(answer)},
    }


def _operation(root: Path) -> dict:
    files = _write_inputs(root)
    return {
        **files, "allow_commands": False, "strict": False, "json": True,
        "stream": False,
        "data_refs": [
            f"data_output_check.contract:{files['contract']['sha256'][:32]}",
            f"data_output_check.answer:{files['answer']['sha256'][:32]}",
        ],
        "credential_refs": [],
    }


def test_output_check_route_uses_operation_lifecycle_and_seals_action(tmp_path):
    head = JourneyStore(tmp_path).create(MutationCommand(
        OWNER, JOURNEY, None, "create", "intake",
        {"legacy_label": None, "goal": "output check", "intake": {},
         "occurred_at": NOW})).event_head_sha256
    operation = _operation(tmp_path)
    prepared, p_status = gateway_grant_post(
        "/api/gateway-grants/prepare/output.check", json.dumps({
            "schema": "flywheel.gateway-operation/v1",
            "journey_ref": JOURNEY, "expected_event_head": head,
            "client_request_id": "output-check-1",
            "operation": operation}).encode(),
        owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW,
        workspace_root=tmp_path)
    approved, a_status = gateway_grant_post(
        "/api/gateway-grants/approve-once",
        json.dumps({"proposal_ref": prepared["proposal_ref"]}).encode(),
        owner_ref=OWNER, state_root=tmp_path, clock=lambda: NOW)
    assert (p_status, a_status) == (200, 200)

    captures = []

    class StubProcess:
        def resume(self): return True
        def signal_tree(self): return True
        def close(self): pass
        def wait(self, _timeout):
            private = json.loads(captures[0].stdin_bytes)
            assert private["operation"] == operation
            assert private["repo_root"] == str(tmp_path)
            result = {"verdict": "PASS", "release": "RELEASE",
                      "cli_exit_code": 0, "fields": []}
            output = b"\n".join([
                canonical_bytes({"type": "progress",
                                 "event": {"phase": "checking"}}),
                canonical_bytes({"type": "terminal", "state": "completed",
                                 "result": result}), b""])
            return ProcessOutcome(0, output.decode("utf-8"), "", 1, False)

    def launcher(spec):
        captures.append(spec)
        return StubProcess()

    service = GatewayOperations(tmp_path, clock=lambda: NOW, lock_timeout_s=5,
        credential_resolver=lambda authorized, _root: replace(
            authorized, credential_bindings={}))
    raw = json.dumps({"schema": "flywheel.gateway-operation/v1",
        "journey_ref": JOURNEY, "expected_event_head": head,
        "client_request_id": "output-check-1",
        "grant_ref": approved["grant_ref"], **operation}).encode()

    response = route_gateway_operation(
        "POST", "/api/output/check", owner_ref=OWNER, raw=raw,
        content_type="application/json", service=service,
        process_factory=GatewayOutputCheckProcessFactory(
            repo_root=tmp_path, run_root=tmp_path / "run",
            state_root=tmp_path, launcher=launcher))

    assert response.status == 200
    assert response.body["verdict"] == "PASS"
    op_ref = operation_ref_for(OWNER, JOURNEY, "output-check-1")
    sealed = service.result(OWNER, op_ref)
    assert sealed["action"] == "output.check"
    assert sealed["result"]["verdict"] == "PASS"
