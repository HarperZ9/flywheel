#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Flywheel evaluation reporter.

This optional reporter turns a bounded Flywheel JSON report into two caller-
persisted byte artifacts and an EMET witness receipt over those bytes. EMET
witnesses artifact integrity only; it does not verify Flywheel scores, statuses,
incident conclusions, or semantic truth.
"""
import hashlib
import json
import math
import os

from emet import report, witness_receipt

RAW_REPORT_FILENAME = "flywheel-evaluation.json"
RECORD_FILENAME = "flywheel-record.json"
RECORD_SCHEMA = "emet-flywheel-evaluation-record/v2"
PACKET_FILENAME = "flywheel-process-audit-packet.json"
PACKET_RECORD_FILENAME = "flywheel-process-audit-record.json"
PACKET_RECEIPT_FILENAME = "flywheel-process-audit-receipt.json"
PACKET_COMMITMENT_FILENAME = "flywheel-process-audit-commitment.json"
PACKET_RECORD_SCHEMA = "emet-flywheel-process-audit-packet-record/v2"
PACKET_COMMITMENT_SCHEMA = "emet-flywheel-packet-commitment/v2"
MAX_BYTES = 16 * 1024 * 1024
MAX_DEPTH = 32
_PROCESS_AUDIT_SCHEMA = "flywheel.incident-sim-process-audit/v1"
_PACKET_ARTIFACT_NAMES = frozenset({PACKET_FILENAME, PACKET_RECORD_FILENAME})
_KNOWN_SCHEMAS = {"flywheel.inspect-evidence/v1", "flywheel.incident-sim-command/v1",
                  _PROCESS_AUDIT_SCHEMA}
_INSPECT_STATUSES = {"started", "success", "cancelled", "error"}
_INSPECT_ASSESSMENTS = {"reported", "incomplete", "error"}
_INSPECT_SEMANTIC = {"UNVERIFIABLE"}
_INCIDENT_VERDICTS = {"MATCH", "DRIFT", "UNVERIFIABLE"}


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("E_DUPLICATE_KEY")
        out[key] = value
    return out


def _nonfinite(token):
    raise ValueError("E_NONFINITE_NUMBER")


def _finite_float(token):
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("E_NONFINITE_NUMBER")
    return value


def _depth(value):
    max_depth = 0
    stack = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        if depth > max_depth:
            max_depth = depth
        if max_depth > MAX_DEPTH:
            return max_depth
        if isinstance(item, dict):
            for child in item.values():
                stack.append((child, depth + 1))
        elif isinstance(item, list):
            for child in item:
                stack.append((child, depth + 1))
    return max_depth


def _load(raw):
    if not isinstance(raw, bytes):
        raise ValueError("E_TYPE")
    if len(raw) > MAX_BYTES:
        raise ValueError("E_TOO_LARGE")
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise ValueError("E_UTF8") from exc
    try:
        value = json.loads(text, object_pairs_hook=_pairs,
                           parse_constant=_nonfinite, parse_float=_finite_float)
    except RecursionError as exc:
        raise ValueError("E_TOO_DEEP") from exc
    except ValueError as exc:
        if str(exc).startswith("E_"):
            raise
        raise ValueError("E_JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("E_TOP_LEVEL")
    if _depth(value) > MAX_DEPTH:
        raise ValueError("E_TOO_DEEP")
    return value


def _text(value):
    return isinstance(value, str) and bool(value)


def _enum(value, allowed):
    if not _text(value):
        raise ValueError("E_SHAPE")
    if value not in allowed:
        raise ValueError("E_ENUM")
    return value


def _string_list(value):
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _scope_list(value):
    """The producer's scope list. Flywheel names it `scope`; older Flywheel
    output names it `does_not_prove`. Either name is accepted."""
    return value.get("scope", value.get("does_not_prove"))


def _inspect_projection(value):
    if not isinstance(value.get("producer"), dict):
        raise ValueError("E_SHAPE")
    if not isinstance(value.get("source"), dict):
        raise ValueError("E_SHAPE")
    if not isinstance(value.get("source_pointers"), list):
        raise ValueError("E_SHAPE")
    if not _string_list(_scope_list(value)):
        raise ValueError("E_SHAPE")
    if not isinstance(value.get("invalidated"), bool):
        raise ValueError("E_SHAPE")
    reported_status = _enum(value.get("reported_status"), _INSPECT_STATUSES)
    assessment = _enum(value.get("assessment"), _INSPECT_ASSESSMENTS)
    semantic = _enum(value.get("semantic_verification"), _INSPECT_SEMANTIC)
    return {
        "reported_status": reported_status,
        "assessment": assessment,
        "semantic_verification": semantic,
        "invalidated": "true" if value["invalidated"] else "false",
    }


def _overall_verdict_from(value):
    evaluation = value.get("evaluation")
    if not isinstance(evaluation, dict):
        packet = value.get("audit_packet")
        evaluation = packet.get("evaluation") if isinstance(packet, dict) else None
    overall = evaluation.get("overall") if isinstance(evaluation, dict) else None
    verdict = overall.get("verdict") if isinstance(overall, dict) else None
    return _enum(verdict, _INCIDENT_VERDICTS)


def _incident_projection(value):
    if not isinstance(value.get("sources"), dict):
        raise ValueError("E_SHAPE")
    if not isinstance(value.get("audit_packet"), dict):
        raise ValueError("E_SHAPE")
    if not _string_list(_scope_list(value)):
        raise ValueError("E_SHAPE")
    return {"evaluation_overall_verdict": _overall_verdict_from(value)}


def _process_audit_projection(value):
    if not isinstance(value.get("receipts"), dict):
        raise ValueError("E_SHAPE")
    if not isinstance(value.get("receipt_verification"), dict):
        raise ValueError("E_SHAPE")
    if not isinstance(value.get("source_values"), list):
        raise ValueError("E_SHAPE")
    if not isinstance(value.get("independence"), dict):
        raise ValueError("E_SHAPE")
    return {"evaluation_overall_verdict": _overall_verdict_from(value)}


def _projection(value):
    schema = value.get("schema")
    if not isinstance(schema, str):
        raise ValueError("E_SCHEMA")
    if schema not in _KNOWN_SCHEMAS:
        raise ValueError("E_SCHEMA")
    if schema == "flywheel.inspect-evidence/v1":
        return schema, _inspect_projection(value)
    if schema == _PROCESS_AUDIT_SCHEMA:
        return schema, _process_audit_projection(value)
    return schema, _incident_projection(value)


def _record(raw, record_schema, raw_name, record_name):
    value = _load(raw)
    producer_schema, producer_claims = _projection(value)
    return {
        "schema": record_schema,
        "producer_schema": producer_schema,
        "source": {
            "algorithm": "sha256",
            "byte_length": len(raw),
            "sha256": _sha256(raw),
        },
        "producer_claims": producer_claims,
        "artifact_names": {
            "raw": raw_name,
            "record": record_name,
        },
        "semantic_conclusions_verified_by_emet": "UNVERIFIED",
        "scope": [
            "the sha256 and byte length of the exact Flywheel bytes",
            "the producer fields copied from those bytes as Flywheel reported them",
        ],
    }


def build_eval_record(raw):
    """Build a canonical-safe metadata record for exact raw Flywheel bytes."""
    return _record(raw, RECORD_SCHEMA, RAW_REPORT_FILENAME, RECORD_FILENAME)


def build_packet_record(raw):
    """Build metadata for exact Flywheel process-audit packet bytes."""
    record = _record(raw, PACKET_RECORD_SCHEMA, PACKET_FILENAME, PACKET_RECORD_FILENAME)
    if record["producer_schema"] != _PROCESS_AUDIT_SCHEMA:
        raise ValueError("E_SCHEMA")
    return record


def mint_receipt(raw, now=None):
    """Return an EMET receipt and caller-persisted artifact bytes."""
    record = build_eval_record(raw)
    record_bytes = report.canonical(record).encode("utf-8")
    artifacts = {
        RAW_REPORT_FILENAME: raw,
        RECORD_FILENAME: record_bytes,
    }
    env = {
        "command": "anchor",
        "results": [
            {"path": RAW_REPORT_FILENAME, "sha256": _sha256(raw)},
            {"path": RECORD_FILENAME, "sha256": _sha256(record_bytes)},
        ],
    }
    receipt = witness_receipt.emit_receipt(env, now=now)
    return receipt, artifacts



def _receipt_bytes(receipt):
    return report.canonical(receipt).encode("utf-8")


def _commitment(raw, record_bytes, receipt):
    receipt_bytes = _receipt_bytes(receipt)
    return {
        "schema": PACKET_COMMITMENT_SCHEMA,
        "packet_artifact": PACKET_FILENAME,
        "record_artifact": PACKET_RECORD_FILENAME,
        "receipt_artifact": PACKET_RECEIPT_FILENAME,
        "packet_sha256": _sha256(raw),
        "record_sha256": _sha256(record_bytes),
        "receipt_id": receipt["receipt_id"],
        "receipt_sha256": _sha256(receipt_bytes),
        "subject_paths": [row.get("path") for row in receipt.get("subject", [])],
        "separate_retention_required": True,
        "emet_stores_commitment_independently": False,
        "scope": [
            "the sha256 of the packet, the record and the receipt",
            "the receipt id and the subject paths it names",
        ],
    }


def _require_packet_artifacts(artifacts):
    if not isinstance(artifacts, dict):
        raise ValueError("E_ARTIFACTS")
    if frozenset(artifacts) != _PACKET_ARTIFACT_NAMES:
        raise ValueError("E_ARTIFACT_KEYS")
    checked = {}
    for name in (PACKET_FILENAME, PACKET_RECORD_FILENAME):
        data = artifacts[name]
        if not isinstance(data, bytes):
            raise ValueError("E_ARTIFACT_BYTES")
        checked[name] = data
    return checked


def _portable_output_name(name):
    return (
        isinstance(name, str)
        and name
        and name not in {".", ".."}
        and not os.path.isabs(name)
        and os.path.basename(name) == name
        and "/" not in name
        and "\\" not in name
    )


def _packet_outputs(receipt, artifacts, commitment):
    checked = _require_packet_artifacts(artifacts)
    outputs = {
        PACKET_FILENAME: checked[PACKET_FILENAME],
        PACKET_RECORD_FILENAME: checked[PACKET_RECORD_FILENAME],
        PACKET_RECEIPT_FILENAME: _receipt_bytes(receipt),
        PACKET_COMMITMENT_FILENAME: report.canonical(commitment).encode("utf-8"),
    }
    if not all(_portable_output_name(name) for name in outputs):
        raise ValueError("E_OUTPUT_NAME")
    return outputs


def _write_exclusive(paths, outputs):
    handles = {}
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        for name, path in paths.items():
            fd = None
            try:
                fd = os.open(path, flags, 0o666)
                handles[name] = os.fdopen(fd, "wb")
                fd = None
            finally:
                if fd is not None:
                    os.close(fd)
        for name, handle in handles.items():
            handle.write(outputs[name])
    finally:
        for handle in handles.values():
            handle.close()


def mint_packet_receipt(raw, now=None):
    """Return a packet receipt, fixed-name artifacts, and reviewer commitment.

    The receipt witnesses exact packet bytes and a bounded metadata record. It does
    not store the commitment independently; callers must retain the returned
    receipt hash or commitment outside the packet-local digest graph.
    """
    record = build_packet_record(raw)
    record_bytes = report.canonical(record).encode("utf-8")
    artifacts = {
        PACKET_FILENAME: raw,
        PACKET_RECORD_FILENAME: record_bytes,
    }
    env = {
        "command": "anchor",
        "results": [
            {"path": PACKET_FILENAME, "sha256": _sha256(raw)},
            {"path": PACKET_RECORD_FILENAME, "sha256": _sha256(record_bytes)},
        ],
    }
    receipt = witness_receipt.emit_receipt(env, now=now)
    return receipt, artifacts, _commitment(raw, record_bytes, receipt)


def write_packet_artifacts(out_dir, receipt, artifacts, commitment):
    """Persist packet artifacts without clobbering existing files.

    The caller controls storage. This helper validates the two caller-provided
    artifact names before creating the directory, writes only fixed public
    artifact names, and raises FileExistsError for existing outputs including
    dangling links. If an output appears after preflight, exclusive creation
    fails closed; already reserved files may remain for inspection and are not
    cleaned up automatically.
    """
    outputs = _packet_outputs(receipt, artifacts, commitment)
    os.makedirs(out_dir, exist_ok=True)
    paths = {name: os.path.join(out_dir, name) for name in outputs}
    for path in paths.values():
        if os.path.lexists(path):
            raise FileExistsError(path)
    _write_exclusive(paths, outputs)
    return paths
