from __future__ import annotations

import base64
import hashlib

from .evidence_json import strict_load_json
from .inspect_upload_metadata import MAX_INSPECT_UPLOAD_BYTES, sanitize_inspect_filename, valid_inspect_sha256

UNIT_CONTRACT_UPLOAD_MEDIA_TYPE = "application/vnd.flywheel.inspect-import-with-unit-contract+json"
REQUEST_SCHEMA = "flywheel.inspect-import-with-unit-contract-request/v1"
MAX_ENVELOPE_BYTES = MAX_INSPECT_UPLOAD_BYTES * 3


def read_unit_contract_upload(handler) -> tuple[dict, bytes, bytes, str | None]:
    length = handler._content_length()
    if length is None or length <= 0:
        return {}, b"", b"", "INVALID_LENGTH"
    if length > MAX_ENVELOPE_BYTES:
        return {}, b"", b"", "PAYLOAD_TOO_LARGE"
    try:
        req = strict_load_json(handler.rfile.read(length), max_bytes=MAX_ENVELOPE_BYTES, max_depth=12)
        if req.get("schema") != REQUEST_SCHEMA:
            raise ValueError
        filename = sanitize_inspect_filename(req.get("filename", ""))
        expected_sha = req.get("inspect_sha256")
        expected_len = req.get("inspect_byte_length")
        if not valid_inspect_sha256(expected_sha) or type(expected_len) is not int:
            raise ValueError
        raw = _b64(req.get("inspect_json_base64"))
        unit = _b64(req.get("unit_contract_json_base64"))
    except (TypeError, ValueError):
        return {}, b"", b"", "INVALID_REQUEST"
    actual = hashlib.sha256(raw).hexdigest()
    if len(raw) != expected_len or actual != expected_sha:
        return {}, b"", b"", "SOURCE_DIGEST_MISMATCH"
    declared = {"length": len(raw), "digest": actual, "filename": filename}
    return declared, raw, unit, None


def _b64(value: object) -> bytes:
    if type(value) is not str:
        raise ValueError
    data = base64.b64decode(value.encode("ascii"), validate=True)
    if not 0 < len(data) <= MAX_INSPECT_UPLOAD_BYTES:
        raise ValueError
    return data
