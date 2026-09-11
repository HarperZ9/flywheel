"""Authenticated operation-bound, one-record private detail responses."""
from urllib.parse import parse_qs
import base64

from .gateway_agent_trace import AgentTrace, TraceError
from .gateway_operation import GatewayOperationError
from .evidence_json import canonical_bytes


def read_trace(service, owner_ref: str, operation_ref: str, query: str) -> dict:
    values = parse_qs(query, keep_blank_values=True, strict_parsing=True)
    if (set(values) != {"ref", "sequence"}
            or any(len(v) != 1 for v in values.values())):
        raise GatewayOperationError("INVALID_REQUEST")
    ref, sequence = values["ref"][0], values["sequence"][0]
    import re
    if (re.fullmatch(r"agt_[0-9a-f]{32}", ref) is None
            or re.fullmatch(r"0|[1-9][0-9]{0,3}", sequence) is None
            or int(sequence) >= 2048):
        raise GatewayOperationError("INVALID_REQUEST")
    # Never accept owner/Journey from the query; existing operation authority
    # decides them before opening the private store.
    snapshot = service.snapshot(owner_ref, operation_ref)
    try:
        trace = AgentTrace(service.state_root, owner_ref, snapshot.journey_ref, operation_ref)
        if ref != trace.ref:
            raise GatewayOperationError("NOT_FOUND")
        records = trace.read_reference(ref)
        if not records or int(sequence) >= len(records):
            raise GatewayOperationError("NOT_FOUND")
        if snapshot.state in {"completed", "failed", "cancelled"}:
            result = service.result(owner_ref, operation_ref)["result"]
            if result.get("trace_ref") == ref and (
                    result.get("record_count") != len(records)
                    or result.get("trace_head_sha256") != trace.head):
                raise TraceError()
        record = records[int(sequence)]
        return {"schema": "flywheel.gateway-agent-trace-detail/v1",
            "trace_ref": ref, "operation_ref": operation_ref,
            "journey_ref": snapshot.journey_ref, "record_count": len(records),
            "trace_head_sha256": trace.head, "record": record,
            "record_canonical_base64": base64.b64encode(canonical_bytes({
                k: v for k, v in record.items() if k != "record_sha256"})).decode("ascii"),
            "next_sequence": int(sequence) + 1 if int(sequence) + 1 < len(records) else None,
            "does_not_prove": ["NOT_SEMANTIC_TRUTH", "NOT_UNLIMITED_TOOL_OUTPUT"]}
    except TraceError:
        raise GatewayOperationError("STORE_COMMIT_FAILED") from None
