"""Descriptor-backed Writing operation contracts for HTTP, CLI and MCP."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit
from typing import Any, Callable

from .evidence_public import ERROR_SCHEMA, TransportError, exact_request

SCHEMA = "flywheel.writing-operations/v1"
@dataclass(frozen=True)
class Field:
    name: str
    json_type: str
    description: str = ""

    def schema(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": self.json_type}
        if self.description:
            out["description"] = self.description
        return out


@dataclass(frozen=True)
class Operation:
    operation_id: str
    description: str
    service_adapter: str
    http_method: str
    http_path: str
    http_fields: tuple[Field, ...] = ()
    http_optional: tuple[Field, ...] = ()
    http_payload: str = "none"
    mcp_tool: str = ""
    mcp_fields: tuple[Field, ...] = ()
    mcp_optional: tuple[Field, ...] = ()
    mcp_payload: str = "json-object"
    mcp_available: bool = True
    mcp_unavailable_reason: str = ""
    cli_available: bool = True
    schema: str = SCHEMA

    def http_required_fields(self) -> list[str]:
        return [f.name for f in self.http_fields]

    def mcp_required_fields(self) -> list[str]:
        return [f.name for f in self.mcp_fields]

    def mcp_schema(self) -> dict[str, Any]:
        fields = self.mcp_fields + self.mcp_optional
        return _object_schema(fields, self.mcp_required_fields())

    def openapi_operation(self, tag: str) -> dict[str, Any]:
        out: dict[str, Any] = {
            "summary": self.description,
            "operationId": self.operation_id.replace(".", "_"),
            "tags": [tag],
            "responses": _responses(),
            "security": [{"bearerAuth": []}],
            "x-flywheel-custody": "private",
            "x-flywheel-operation-schema": self.schema,
            "x-flywheel-service-adapter": self.service_adapter,
            "x-flywheel-transport-availability": transport_availability(self),
            "x-flywheel-transport-error-schema": ERROR_SCHEMA,
        }
        if self.mcp_unavailable_reason:
            out["x-flywheel-mcp-unavailable-reason"] = self.mcp_unavailable_reason
        if self.http_method == "POST":
            fields = self.http_fields + self.http_optional
            out["requestBody"] = {"required": True, "content": {
                "application/json": {"schema": _object_schema(
                    fields, self.http_required_fields())}}}
        elif self.http_fields:
            out["parameters"] = [{
                "name": f.name, "in": "query", "required": True,
                "schema": f.schema(), "description": f.description}
                for f in self.http_fields]
        return out


def _f(name: str, json_type: str = "string", description: str = "") -> Field:
    return Field(name, json_type, description)
S = lambda name, description="": _f(name, "string", description)
O = lambda name, description="": _f(name, "object", description)
HOME = S("home", "optional local Flywheel home for stdio MCP")
COMMON = (S("journey_ref"), S("expected_event_head"), S("client_request_id"))
PROJECT = (*COMMON[:2], S("project_ref"), COMMON[2])


OPERATIONS: tuple[Operation, ...] = (
    Operation("writing.status", "List owner-local writing projects.", "status",
        "GET", "/api/writing/status", mcp_tool="writing.status",
        mcp_optional=(HOME,)),
    Operation("writing.doctor", "Report local writing workflow readiness.",
        "doctor", "GET", "/api/writing/doctor", mcp_tool="writing.doctor",
        mcp_optional=(HOME,)),
    Operation("writing.project_get", "Read a public project view.",
        "project_state", "GET", "/api/writing/project",
        http_fields=(S("journey_ref"),), cli_available=False),
    Operation("writing.project_init", "Prepare a project init proposal.",
        "prepare_init", "POST", "/api/writing/init/prepare",
        http_fields=(O("brief"), O("source_packet"), S("client_request_id")),
        http_payload="embedded-json-objects",
        mcp_tool="writing.project_init",
        mcp_fields=(S("brief_path"), S("source_packet_path"),
                    S("client_request_id")),
        mcp_optional=(HOME,), mcp_payload="local-paths"),
    Operation("writing.section_record", "Prepare a section proposal.",
        "prepare_section", "POST", "/api/writing/section/prepare",
        http_fields=(*COMMON[:2], S("client_request_id"), O("section")),
        mcp_tool="writing.section_record",
        mcp_fields=(*COMMON[:2], O("section"), S("client_request_id")),
        mcp_optional=(HOME,)),
    Operation("writing.revision_record", "Prepare a revision proposal.",
        "prepare_revision", "POST", "/api/writing/revision/prepare",
        http_fields=(*PROJECT[:3], S("section_ref"), S("body"), PROJECT[3]),
        mcp_tool="writing.revision_record",
        mcp_fields=(*PROJECT[:3], S("section_ref"), S("body"), PROJECT[3]),
        mcp_optional=(HOME,)),
    Operation("writing.diagnose", "Prepare a reader-flow diagnostic proposal.",
        "prepare_diagnose", "POST", "/api/writing/diagnose/prepare",
        http_fields=(*PROJECT[:3], S("revision_ref"), PROJECT[3]),
        mcp_tool="writing.diagnose",
        mcp_fields=(*PROJECT[:3], S("revision_ref"), PROJECT[3]),
        mcp_optional=(HOME,)),
    Operation("writing.card_record", "Prepare an author card proposal.",
        "prepare_card", "POST", "/api/writing/card/prepare",
        http_fields=(*COMMON[:2], S("client_request_id"), O("card")),
        mcp_tool="writing.card_record",
        mcp_fields=(*COMMON[:2], O("card"), S("client_request_id")),
        mcp_optional=(HOME,)),
    Operation("writing.candidate_record",
        "Prepare a scoped candidate proposal.", "prepare_candidate",
        "POST", "/api/writing/candidate/prepare",
        http_fields=(*PROJECT[:3], S("card_ref"), S("body"), PROJECT[3]),
        mcp_tool="writing.candidate_record",
        mcp_fields=(*PROJECT[:3], S("card_ref"), S("body"), PROJECT[3]),
        mcp_optional=(HOME,)),
    Operation("writing.decision_record",
        "Prepare an accept/reject/rollback proposal.", "prepare_decision",
        "POST", "/api/writing/decision/prepare",
        http_fields=(*PROJECT[:3], S("decision"), PROJECT[3]),
        http_optional=(S("candidate_ref"), S("section_ref"),
                       S("to_revision_ref"), S("reason")),
        mcp_tool="writing.decision_record",
        mcp_fields=(*PROJECT[:3], S("decision"), PROJECT[3]),
        mcp_optional=(HOME, S("candidate_ref"), S("section_ref"),
                      S("to_revision_ref"), S("reason"))),
    Operation("writing.review_prepare", "Prepare an unmeasured review proposal.",
        "prepare_review", "POST", "/api/writing/review/prepare",
        http_fields=PROJECT, mcp_tool="writing.review_prepare",
        mcp_fields=PROJECT, mcp_optional=(HOME,)),
    Operation("writing.export_prepare", "Prepare a manuscript export proposal.",
        "prepare_export", "POST", "/api/writing/export/prepare",
        http_fields=(*PROJECT[:3], S("out_ref"), PROJECT[3]),
        mcp_tool="writing.export_prepare",
        mcp_fields=(*PROJECT[:3], S("out_ref"), PROJECT[3]),
        mcp_optional=(HOME,)),
    Operation("writing.proposal_get", "Inspect an exact proposal preview.",
        "proposal_get", "POST", "/api/writing/proposal/get",
        http_fields=(S("proposal_ref"),), mcp_tool="writing.proposal_get",
        mcp_fields=(S("proposal_ref"),), mcp_optional=(HOME,)),
    Operation("writing.proposal_approve", "Approve a proposal over private HTTP.",
        "approve_proposal", "POST", "/api/writing/proposal/approve",
        http_fields=(S("proposal_ref"),), mcp_tool="writing.proposal_approve",
        mcp_fields=(S("proposal_ref"),), mcp_optional=(HOME,),
        mcp_available=False, mcp_unavailable_reason="APPROVAL_UNAVAILABLE"),
    Operation("writing.proposal_commit",
        "Commit a proposal with an externally approved grant.",
        "commit_proposal", "POST", "/api/writing/proposal/commit",
        http_fields=(S("proposal_ref"), S("grant_ref")),
        mcp_tool="writing.proposal_commit",
        mcp_fields=(S("proposal_ref"), S("grant_ref")), mcp_optional=(HOME,)),
    Operation("writing.project_get_post", "Read a public project view.",
        "project_state", "POST", "/api/writing/project/get",
        http_fields=(S("journey_ref"),), cli_available=False),
)

_HTTP = {(op.http_method, op.http_path): op for op in OPERATIONS}
_MCP = {op.mcp_tool: op for op in OPERATIONS if op.mcp_tool}


def operation_for_http(method: str, path: str) -> Operation:
    route = urlsplit(path).path
    return _HTTP[(method.upper(), route)]


def operation_for_mcp(name: str) -> Operation:
    return _MCP[name]


def http_operations() -> tuple[Operation, ...]:
    return tuple(op for op in OPERATIONS if op.http_path)


def mcp_tool_descriptors() -> list[dict[str, Any]]:
    tools = []
    for op in OPERATIONS:
        if not op.mcp_tool:
            continue
        tool = {"name": op.mcp_tool, "description": _mcp_description(op),
                "inputSchema": op.mcp_schema(),
                "x-flywheel-operation-schema": op.schema,
                "x-flywheel-transport-availability":
                    transport_availability(op)}
        if op.mcp_unavailable_reason:
            tool["x-flywheel-mcp-unavailable-reason"] = (
                op.mcp_unavailable_reason)
        tools.append(tool)
    return tools


def mcp_schemas() -> dict[str, dict[str, Any]]:
    return {tool["name"]: tool["inputSchema"] for tool in mcp_tool_descriptors()}


def validate_http_payload(op: Operation, value: dict) -> dict:
    return _validate(value, op.http_fields, op.http_optional)


def validate_mcp_arguments(op: Operation, value: object) -> dict:
    if type(value) is not dict:
        raise TransportError("INVALID_ARGUMENTS", "arguments must be an object")
    return _validate(value, op.mcp_fields, op.mcp_optional)


def openapi_path_items(group: Callable[[str], str]) -> dict[str, dict[str, Any]]:
    paths: dict[str, dict[str, Any]] = {}
    for op in http_operations():
        entry = paths.setdefault(op.http_path, {"x-flywheel-match": "descriptor"})
        entry[op.http_method.lower()] = op.openapi_operation(group(op.http_path))
    return paths


def transport_availability(op: Operation) -> dict[str, Any]:
    payload = (op.http_payload if op.http_payload != "none" else
        "json-object" if op.http_method == "POST" else
        "query-string" if op.http_fields else "none")
    availability: dict[str, Any] = {
        "http": {"available": True, "custody": "private-bearer",
                 "payload": payload}}
    if op.cli_available:
        availability["cli"] = {"available": True, "custody": "local-process"}
    if op.mcp_tool:
        availability["mcp"] = {"available": op.mcp_available,
            "custody": "local-stdio", "payload": op.mcp_payload}
        if op.mcp_unavailable_reason:
            availability["mcp"]["reason"] = op.mcp_unavailable_reason
    return availability


def _validate(value: dict, required: tuple[Field, ...],
              optional: tuple[Field, ...]) -> dict:
    out = exact_request(value, {f.name for f in required},
                        optional={f.name for f in optional})
    field_map = {f.name: f for f in (*required, *optional)}
    for name, spec in field_map.items():
        if name in out and not _matches(out[name], spec.json_type):
            raise TransportError(
                "INVALID_FIELD_TYPE", f"{name} has invalid field type", 422)
    return out


def _matches(value: object, json_type: str) -> bool:
    if json_type == "string":
        return type(value) is str
    if json_type == "object":
        return type(value) is dict
    raise AssertionError(f"unsupported writing field type: {json_type}")


def _object_schema(fields: tuple[Field, ...], required: list[str]
                   ) -> dict[str, Any]:
    return {"type": "object", "required": required,
        "additionalProperties": False,
        "properties": {f.name: f.schema() for f in fields},
        "x-flywheel-operation-schema": SCHEMA}


def _responses() -> dict[str, Any]:
    responses = {"200": {"description": "writing operation response",
        "content": {"application/json": {"schema": {"type": "object"}}}}}
    for status in ("400", "404", "409", "422", "500"):
        responses[status] = {"description": "typed transport error",
            "content": {"application/json": {"schema": _error_schema()}}}
    return responses


def _error_schema() -> dict[str, Any]:
    return {"type": "object", "required": ["schema", "error"],
        "properties": {"schema": {"const": ERROR_SCHEMA},
        "error": {"type": "object", "required": ["code", "message"],
        "properties": {"code": {"type": "string"},
        "message": {"type": "string"}}}}}


def _mcp_description(op: Operation) -> str:
    if op.mcp_unavailable_reason == "APPROVAL_UNAVAILABLE":
        return "Unavailable over MCP; approve by CLI or private HTTP."
    return op.description
