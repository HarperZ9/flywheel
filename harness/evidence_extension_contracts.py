"""evidence_extension_contracts.py -- fail-closed contextual capabilities.

The capability document binds Incident Compiler, Frontier Claims, and
Domain Packs to accepted schemas and accepted receipts, and to the one
containment fact. Rows derive only from accepted contracts; a contract
whose operations need process containment stays execution_locked until
that fact is accepted. authorize_capability is a pure read: it never
consumes a grant, never dispatches, and never grants by absence.
"""
from __future__ import annotations

from .evidence_json import canonical_sha256

SCHEMA = "flywheel.evidence-capabilities/v1"
_JOURNEY_SCHEMA = "flywheel.evidence-journey-projection/v2"
_PACKET_SCHEMA = "flywheel.evidence-packet/v1"
_STATES = ("read_only", "data_only", "execution_locked", "available")
_ROW_FIELDS = {
    "id", "schema", "state", "operations", "journey_schema",
    "packet_schema", "containment_class", "limits", "reason",
    "contract_sha256", "acceptance_receipt_sha256",
}
#: The accepted operation vocabulary per contract schema. Anything else
#: is unknown and refused: an operation this document never accepted
#: cannot travel under an accepted schema's name.
_OPERATIONS = {
    "flywheel.incident-case/v1": {"incident.propose"},
    "flywheel.frontier-claim/v1": {"frontier.project",
                                   "frontier.axis.append"},
    "flywheel.domain-pack/v1": {"pack.project", "pack.qa"},
}


def _refuse(message: str) -> None:
    raise ValueError(message)


def _accepted_receipt(contract: dict) -> str:
    receipt = contract.get("acceptance_receipt")
    if not isinstance(receipt, dict) or receipt.get("accepted") is not True:
        _refuse("capability contract lacks an accepted receipt")
    if not isinstance(receipt.get("receipt_sha256"), str):
        _refuse("capability contract receipt lacks a digest")
    return canonical_sha256(receipt)


def _row(capability_id: str, contract: dict, containment: dict) -> dict:
    schema = contract.get("schema")
    operations = contract.get("operations")
    limits = contract.get("limits")
    if not isinstance(schema, str) or not schema.startswith("flywheel."):
        _refuse("capability contract names an unknown schema")
    if (not isinstance(operations, list) or not operations
            or any(not isinstance(op, str)
                   or op not in _OPERATIONS.get(schema, set())
                   for op in operations)):
        _refuse("capability operations are missing or not admissible")
    if not isinstance(limits, dict) or not limits:
        _refuse("capability contract declares no limits")
    receipt_sha = _accepted_receipt(contract)
    executable = bool(contract.get("data_only") is not True)
    if containment.get("process") is True:
        state = "available"
        reason = "accepted with containment"
    elif executable:
        state = "execution_locked"
        reason = "process containment not accepted"
    else:
        state = "execution_locked"
        reason = "data admissible; process containment not accepted"
    return {
        "id": capability_id,
        "schema": schema,
        "state": state,
        "operations": sorted(operations),
        "journey_schema": _JOURNEY_SCHEMA,
        "packet_schema": _PACKET_SCHEMA,
        "containment_class": (
            "process_contained" if containment.get("process") is True
            else "unavailable"),
        "limits": limits,
        "reason": reason,
        "contract_sha256": canonical_sha256(contract),
        "acceptance_receipt_sha256": receipt_sha,
    }


def capability_document(
    *,
    journey: dict,
    incident_contract: dict | None,
    frontier_contract: dict | None,
    pack_contracts: list[dict],
    containment: dict,
) -> dict:
    """The fail-closed capability sheet for one journey context."""
    if journey.get("schema") != _JOURNEY_SCHEMA:
        _refuse("journey schema is not the accepted projection schema")
    if not isinstance(journey.get("event_head_sha256"), str):
        _refuse("journey head is missing")
    rows: list[dict] = []
    seen: set[str] = set()
    named = {"incident-compiler": incident_contract,
             "frontier-claims": frontier_contract}
    for capability_id, contract in named.items():
        if contract is None:
            continue
        if capability_id in seen:
            _refuse("duplicate capability id")
        seen.add(capability_id)
        rows.append(_row(capability_id, contract, containment))
    for pack in pack_contracts or []:
        pack_id = pack.get("pack_id")
        if not isinstance(pack_id, str) or pack_id in seen:
            _refuse("duplicate or missing capability id")
        seen.add(pack_id)
        rows.append(_row(pack_id, pack, containment))
    for row in rows:
        if set(row) != _ROW_FIELDS or row["state"] not in _STATES:
            _refuse("capability row is malformed")
    return {
        "schema": SCHEMA,
        "journey_schema": journey["schema"],
        "event_head_sha256": journey["event_head_sha256"],
        "capabilities": rows,
    }


def authorize_capability(
    document: dict,
    *,
    capability_id: str,
    operation: str,
    journey_schema: str,
    packet_schema: str,
    contract_sha256: str,
) -> bool:
    """Pure read: True only when an available row binds this exact
    operation, schemas, and contract hash. Never consumes anything."""
    if document.get("schema") != SCHEMA:
        return False
    for row in document.get("capabilities", []):
        if row.get("id") != capability_id:
            continue
        if row.get("state") == "execution_locked":
            return False
        if operation not in row.get("operations", []):
            return False
        if row.get("journey_schema") != journey_schema:
            return False
        if row.get("packet_schema") != packet_schema:
            return False
        return row.get("contract_sha256") == contract_sha256
    return False
