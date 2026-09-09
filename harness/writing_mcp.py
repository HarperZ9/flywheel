"""Zero-dependency MCP surface for Writing Workspace prepare/commit actions."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .writing_artifacts import WritingArtifactError
from .writing_service import WritingError, WritingService

PROTOCOL = "2025-06-18"
__version__ = "0.1.0"


def _schema(required=(), properties=None):
    return {"type": "object", "required": list(required),
            "additionalProperties": False, "properties": properties or {}}


S, O = {"type": "string"}, {"type": "object"}
COMMON = {"home": S, "journey_ref": S, "expected_event_head": S,
          "client_request_id": S}
PROJECT = {**COMMON, "project_ref": S}
TOOLS = [
    {"name": "writing.status", "description": "List owner-local writing projects.",
     "inputSchema": _schema(properties={"home": S})},
    {"name": "writing.doctor", "description": "Report local writing workflow readiness.",
     "inputSchema": _schema(properties={"home": S})},
    {"name": "writing.project_init", "description": "Prepare a project init proposal.",
     "inputSchema": _schema(("brief_path", "source_packet_path", "client_request_id"),
                            {"home": S, "brief_path": S, "source_packet_path": S,
                             "client_request_id": S})},
    {"name": "writing.section_record", "description": "Prepare a section proposal.",
     "inputSchema": _schema(("journey_ref", "expected_event_head", "section",
                             "client_request_id"), {**COMMON, "section": O})},
    {"name": "writing.revision_record", "description": "Prepare a revision proposal.",
     "inputSchema": _schema(("journey_ref", "expected_event_head", "project_ref",
                             "section_ref", "body", "client_request_id"),
                            {**PROJECT, "section_ref": S, "body": S})},
    {"name": "writing.diagnose", "description": "Prepare a reader-flow diagnostic proposal.",
     "inputSchema": _schema(("journey_ref", "expected_event_head", "project_ref",
                             "revision_ref", "client_request_id"),
                            {**PROJECT, "revision_ref": S})},
    {"name": "writing.card_record", "description": "Prepare an author card proposal.",
     "inputSchema": _schema(("journey_ref", "expected_event_head", "card",
                             "client_request_id"), {**COMMON, "card": O})},
    {"name": "writing.candidate_record", "description": "Prepare a scoped candidate proposal.",
     "inputSchema": _schema(("journey_ref", "expected_event_head", "project_ref",
                             "card_ref", "body", "client_request_id"),
                            {**PROJECT, "card_ref": S, "body": S})},
    {"name": "writing.decision_record", "description": "Prepare an accept/reject/rollback proposal.",
     "inputSchema": _schema(("journey_ref", "expected_event_head", "project_ref",
                             "decision", "client_request_id"),
                            {**PROJECT, "decision": S, "candidate_ref": S,
                             "section_ref": S, "to_revision_ref": S,
                             "reason": S})},
    {"name": "writing.review_prepare", "description": "Prepare an unmeasured review proposal.",
     "inputSchema": _schema(("journey_ref", "expected_event_head", "project_ref",
                             "client_request_id"), PROJECT)},
    {"name": "writing.export_prepare", "description": "Prepare a manuscript export proposal.",
     "inputSchema": _schema(("journey_ref", "expected_event_head", "project_ref",
                             "out_ref", "client_request_id"),
                            {**PROJECT, "out_ref": S})},
    {"name": "writing.proposal_get", "description": "Inspect an exact proposal preview.",
     "inputSchema": _schema(("proposal_ref",), {"home": S, "proposal_ref": S})},
    {"name": "writing.proposal_commit", "description": "Commit with an externally approved grant.",
     "inputSchema": _schema(("proposal_ref", "grant_ref"),
                            {"home": S, "proposal_ref": S, "grant_ref": S})},
    {"name": "writing.proposal_approve", "description": "Unavailable over MCP; approve by CLI.",
     "inputSchema": _schema(("proposal_ref",), {"home": S, "proposal_ref": S})},
]
SCHEMAS = {tool["name"]: tool["inputSchema"] for tool in TOOLS}


def _service(args: dict) -> WritingService:
    home = args.get("home") or os.environ.get(
        "FLYWHEEL_HOME", str(Path.home() / ".flywheel"))
    return WritingService(Path(home))


def _text(value: object) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(value, sort_keys=True)}]}


def _ensure_args(name: str, args: object) -> dict:
    schema = SCHEMAS.get(name)
    if schema is None or type(args) is not dict:
        raise WritingError("INVALID_ARGUMENTS")
    allowed, required = set(schema["properties"]), set(schema["required"])
    if not required.issubset(args) or set(args) - allowed:
        raise WritingError("INVALID_ARGUMENTS")
    for key, spec in schema["properties"].items():
        if key in args and spec["type"] == "string" and type(args[key]) is not str:
            raise WritingError("INVALID_ARGUMENTS")
        if key in args and spec["type"] == "object" and type(args[key]) is not dict:
            raise WritingError("INVALID_ARGUMENTS")
    return args


def _call(params: dict) -> dict:
    try:
        if type(params) is not dict:
            raise WritingError("INVALID_ARGUMENTS")
        name, raw_args = params.get("name"), params.get("arguments", {}) or {}
        args = _ensure_args(name, raw_args)
        svc = _service(args)
        if name == "writing.status":
            return _text(svc.status())
        if name == "writing.doctor":
            return _text(svc.doctor())
        if name == "writing.project_init":
            return _text(svc.prepare_init(
                Path(args["brief_path"]), Path(args["source_packet_path"]),
                client_request_id=args["client_request_id"]))
        if name == "writing.section_record":
            return _text(svc.prepare_section(
                args["journey_ref"], args["expected_event_head"],
                args["section"], client_request_id=args["client_request_id"]))
        if name == "writing.revision_record":
            return _text(svc.prepare_revision(
                args["journey_ref"], args["expected_event_head"], args["project_ref"],
                args["section_ref"], args["body"], client_request_id=args["client_request_id"]))
        if name == "writing.diagnose":
            return _text(svc.prepare_diagnose(
                args["journey_ref"], args["expected_event_head"], args["project_ref"],
                args["revision_ref"], client_request_id=args["client_request_id"]))
        if name == "writing.card_record":
            return _text(svc.prepare_card(
                args["journey_ref"], args["expected_event_head"], args["card"],
                client_request_id=args["client_request_id"]))
        if name == "writing.candidate_record":
            return _text(svc.prepare_candidate(
                args["journey_ref"], args["expected_event_head"], args["project_ref"],
                args["card_ref"], args["body"], client_request_id=args["client_request_id"]))
        if name == "writing.decision_record":
            return _text(svc.prepare_decision(
                args["journey_ref"], args["expected_event_head"], args["project_ref"],
                decision=args["decision"], candidate_ref=args.get("candidate_ref"),
                section_ref=args.get("section_ref"), to_revision_ref=args.get("to_revision_ref"),
                reason=args.get("reason"), client_request_id=args["client_request_id"]))
        if name == "writing.review_prepare":
            return _text(svc.prepare_review(
                args["journey_ref"], args["expected_event_head"], args["project_ref"],
                client_request_id=args["client_request_id"]))
        if name == "writing.export_prepare":
            return _text(svc.prepare_export(
                args["journey_ref"], args["expected_event_head"], args["project_ref"],
                out_ref=args["out_ref"], client_request_id=args["client_request_id"]))
        if name == "writing.proposal_get":
            return _text(svc.proposal_get(args["proposal_ref"]))
        if name == "writing.proposal_commit":
            return _text(svc.commit_proposal(args["proposal_ref"], args["grant_ref"]))
        if name == "writing.proposal_approve":
            return _text({"error": {"code": "APPROVAL_UNAVAILABLE",
                                    "message": "approve writing proposals with the local CLI"}})
        return {"content": [{"type": "text", "text": "unknown writing tool"}],
                "isError": True}
    except (KeyError, TypeError, ValueError, OSError, WritingArtifactError,
            WritingError) as exc:
        return _text({"error": {"code": getattr(exc, "code", str(exc) or "WRITING_FAILED"),
                                "message": "writing workflow is unavailable"}})


def _ok(rid, result):
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def handle_request(req: dict):
    if type(req) is not dict:
        return None
    method, rid = req.get("method"), req.get("id")
    if method == "initialize":
        return _ok(rid, {"protocolVersion": PROTOCOL,
                         "capabilities": {"tools": {}},
                         "serverInfo": {"name": "writing-workspace",
                                        "version": __version__}})
    if method == "tools/list":
        return _ok(rid, {"tools": TOOLS})
    if method == "tools/call":
        return _ok(rid, _call(req.get("params", {})))
    if rid is None:
        return None
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def handle(req: dict):
    return handle_request(req)


def serve(stdin=None, stdout=None) -> int:
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    for line in stdin:
        if not line.strip():
            continue
        try:
            response = handle_request(json.loads(line))
        except json.JSONDecodeError:
            continue
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())
