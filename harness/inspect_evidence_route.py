from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs

from .evidence_json import canonical_bytes
from .evidence_public import TransportError, error_response
from .gateway_envelope import parse_gateway_envelope
from .gateway_grant_errors import gateway_error_response
from .gateway_grant_route import authorize_gateway_envelope
from .gateway_operation import REQUEST_SCHEMA
from .inspect_upload_metadata import (
    INSPECT_MEDIA_TYPES, MAX_INSPECT_UPLOAD_BYTES, inspect_data_ref,
    inspect_operation, sanitize_inspect_filename, valid_inspect_sha256,
    validate_inspect_operation,
)
from .operation_grants import _validate_owner_ref
from .store import (
    _sha as _store_sha, get_entity, latest_audit_for_ref, put_entity,
    query_entities, verify_chain,
)


RESULT_SCHEMA = "flywheel.inspect-import-result/v1"
_CORE_KEYS = {"schema", "source", "data_ref", "report"}
_SOURCE_KEYS = {"format", "sha256", "byte_length", "filename"}


_ERRORS = {
    "INVALID_LENGTH": (400, "Inspect upload length is invalid"),
    "PAYLOAD_TOO_LARGE": (413, "Inspect upload exceeds byte limit"),
    "INVALID_REQUEST": (422, "Inspect upload request is invalid"),
    "SOURCE_DIGEST_MISMATCH": (409, "Inspect upload digest does not match approval"),
    "INSPECT_JSON_REQUIRED": (415, "Inspect upload must be Inspect JSON"),
    "INSPECT_INPUT_REJECTED": (422, "Inspect input was rejected"),
    "REPORT_SOURCE_MISMATCH": (409, "Inspect report source does not match upload"),
    "NOT_FOUND": (404, "Inspect import was not found"),
    "STORE_TAMPERED": (409, "Stored Inspect evidence is inconsistent"),
    "STORE_COMMIT_FAILED": (500, "Inspect evidence could not be stored"),
}
_EID = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")


def _error(code: str) -> tuple[dict, int]:
    status, message = _ERRORS[code]
    return error_response(TransportError(code, message, status))


def _header(headers, name: str) -> str:
    value = headers.get(name)
    return value if type(value) is str else ""


def _declared_headers(handler) -> tuple[dict, tuple[dict, int] | None]:
    headers = handler.headers
    raw_content_length = _header(headers, "Content-Length")
    length = handler._content_length()
    if not raw_content_length or length is None:
        return {}, _error("INVALID_LENGTH")
    try:
        declared_length = int(_header(headers, "X-Flywheel-Inspect-Byte-Length"))
    except ValueError:
        return {}, _error("INVALID_LENGTH")
    if length != declared_length or length <= 0:
        return {}, _error("INVALID_LENGTH")
    if length > MAX_INSPECT_UPLOAD_BYTES:
        return {}, _error("PAYLOAD_TOO_LARGE")
    content_type = (_header(headers, "Content-Type").split(";", 1)[0].strip().lower())
    if content_type not in INSPECT_MEDIA_TYPES:
        return {}, _error("INVALID_REQUEST")
    try:
        filename = sanitize_inspect_filename(_header(headers, "X-Flywheel-Inspect-Filename"))
    except ValueError:
        return {}, _error("INVALID_REQUEST")
    digest = _header(headers, "X-Flywheel-Inspect-Sha256")
    if not valid_inspect_sha256(digest):
        return {}, _error("INVALID_REQUEST")
    return {"length": length, "digest": digest, "filename": filename}, None


def handle_inspect_upload(handler) -> tuple[dict, int]:
    declared, fault = _declared_headers(handler)
    if fault:
        return fault
    raw = handler.rfile.read(declared["length"])
    actual = hashlib.sha256(raw).hexdigest()
    if len(raw) != declared["length"] or actual != declared["digest"]:
        return _error("SOURCE_DIGEST_MISMATCH")
    operation = inspect_operation(actual, len(raw), declared["filename"])
    envelope = {
        "schema": REQUEST_SCHEMA,
        "journey_ref": _header(handler.headers, "X-Flywheel-Journey-Ref"),
        "expected_event_head": _header(handler.headers, "X-Flywheel-Expected-Event-Head"),
        "client_request_id": _header(handler.headers, "X-Flywheel-Client-Request-Id"),
        "grant_ref": _header(handler.headers, "X-Flywheel-Grant-Ref"),
        **operation,
    }
    try:
        parsed = parse_gateway_envelope("import.inspect", canonical_bytes(envelope))
        authorize_gateway_envelope(
            parsed, owner_ref=handler.owner_ref,
            state_root=handler.flywheel_home / "state", clock=handler.clock,
            workspace_root=getattr(handler, "root", None))
    except Exception as exc:
        return gateway_error_response(exc)
    if raw.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")) or declared["filename"].lower().endswith(".eval"):
        return _error("INSPECT_JSON_REQUIRED")
    try:
        report = _import_inspect_log(raw)
    except Exception:
        return _error("INSPECT_INPUT_REJECTED")
    if not _report_matches_upload(report, actual, len(raw)):
        return _error("REPORT_SOURCE_MISMATCH")
    core = _result_core(actual, len(raw), declared["filename"], report)
    record = {"schema": "flywheel.inspect-import-record/v1", "result": core}
    try:
        stored = put_entity("inspect-evidence", record, project=handler.owner_ref,
                            home=_inspect_store_home(handler))
    except Exception:
        return _error("STORE_COMMIT_FAILED")
    if not isinstance(stored, dict) or stored.get("error"):
        return _error("STORE_COMMIT_FAILED")
    return _with_stored(core, stored), 200


def handle_inspect_get(path: str, handler, query: str = "") -> tuple[dict, int] | None:
    if path == "/api/import/inspect":
        return _list_imports(handler, query)
    prefix = "/api/import/inspect/"
    if not path.startswith(prefix):
        return None
    eid = path[len(prefix):]
    if _EID.fullmatch(eid) is None:
        return _error("INVALID_REQUEST")
    return _read_import(handler, eid)


def _inspect_store_home(handler):
    owner = _validate_owner_ref(handler.owner_ref)
    return handler.flywheel_home / "state" / "inspect-evidence" / owner


def _result_core(sha: str, length: int, filename: str, report: dict) -> dict:
    source = {"format": "inspect-json", "sha256": sha, "byte_length": length}
    if filename:
        source["filename"] = filename
    return {"schema": RESULT_SCHEMA, "source": source,
            "data_ref": inspect_data_ref(sha), "report": report}


def _with_stored(core: dict, stored: dict) -> dict:
    return {**core, "stored": {"kind": "inspect-evidence",
            "eid": stored.get("eid", ""), "sha256": stored.get("sha256", ""),
            "chain_hash": stored.get("chain_hash", "")}}


def _report_matches_upload(report: object, sha: str, length: int) -> bool:
    if type(report) is not dict or type(report.get("source")) is not dict:
        return False
    source = report["source"]
    return source.get("sha256") == sha and source.get("byte_length") == length


def _checked_entity(handler, eid: str, *, home=None,
                    chain_verdict: dict | None = None) -> tuple[dict | None, tuple[dict, int] | None]:
    home = home or _inspect_store_home(handler)
    entity = get_entity(eid, home=home)
    if entity is None or entity.get("kind") != "inspect-evidence" or entity.get("project") != handler.owner_ref:
        return None, _error("NOT_FOUND")
    if entity.get("sha256") != _store_sha({"kind": entity["kind"], "project": entity["project"], "data": entity["data"]}):
        return None, _error("STORE_TAMPERED")
    if not _audit_binds_entity(entity, home, chain_verdict=chain_verdict):
        return None, _error("STORE_TAMPERED")
    try:
        record, core = entity["data"], entity["data"]["result"]
        if (record.get("schema") != "flywheel.inspect-import-record/v1"
                or type(core) is not dict or set(core) != _CORE_KEYS
                or core.get("schema") != RESULT_SCHEMA):
            raise ValueError
        source, report = core["source"], core["report"]
        if type(source) is not dict or set(source) - _SOURCE_KEYS:
            raise ValueError
        op_source = {"kind": "client-upload", **source}
        validate_inspect_operation({"source": op_source,
                                    "data_refs": [core["data_ref"]], "credential_refs": []})
        if source.get("format") != "inspect-json" or not _report_matches_upload(report, source["sha256"], source["byte_length"]):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        return None, _error("STORE_TAMPERED")
    return entity, None


def _audit_binds_entity(entity: dict, home, *, chain_verdict: dict | None = None) -> bool:
    audit = latest_audit_for_ref(entity["eid"], home=home)
    chain = chain_verdict if chain_verdict is not None else verify_chain(home=home)
    return (type(audit) is dict
            and audit.get("op") == "put_entity"
            and audit.get("ref") == entity["eid"]
            and audit.get("sha256") == entity["sha256"]
            and audit.get("chain_hash_ok") is True
            and type(chain) is dict
            and chain.get("ok") is True)


def _read_import(handler, eid: str) -> tuple[dict, int]:
    entity, fault = _checked_entity(handler, eid)
    if fault:
        return fault
    return _with_stored(entity["data"]["result"], entity), 200


def _list_imports(handler, query: str) -> tuple[dict, int]:
    params = parse_qs(query or "")
    try:
        limit = max(1, min(int(params.get("limit", ["20"])[0]), 50))
        offset = max(0, int(params.get("offset", ["0"])[0]))
    except (TypeError, ValueError):
        return _error("INVALID_REQUEST")
    home = _inspect_store_home(handler)
    rows = query_entities(kind="inspect-evidence", project=handler.owner_ref,
                          limit=limit, offset=offset,
                          home=home)
    chain_verdict = verify_chain(home=home) if rows else {"ok": True}
    items = []
    for row in rows:
        entity, fault = _checked_entity(handler, row["eid"], home=home,
                                        chain_verdict=chain_verdict)
        if fault:
            return fault
        core = entity["data"]["result"]
        items.append({"eid": entity["eid"], "source": core["source"],
                      "reported_status": core["report"].get("reported_status"),
                      "assessment": core["report"].get("assessment"),
                      "created": entity["created"],
                      "stored": _with_stored(core, entity)["stored"]})
    return {"schema": "flywheel.inspect-import-list/v1",
            "items": items, "limit": limit, "offset": offset}, 200


def _import_inspect_log(raw: bytes) -> dict:
    from .inspect_evidence import import_inspect_log
    return import_inspect_log(raw)
