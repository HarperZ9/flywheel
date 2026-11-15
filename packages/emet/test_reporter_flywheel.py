#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Behavior proof for emet/reporters/flywheel.py.

Uses synthetic Flywheel-shaped JSON bytes only. The reporter never imports or
runs Flywheel and never executes a scorer. Its optional writer persists only
fixed-name packet artifacts into a caller-selected directory. These
checks prove that EMET can bind exact raw Flywheel report bytes and a bounded
metadata projection with a portable witness receipt, while keeping semantic
claims outside EMET's receipt verdict.

Runs under `python -m pytest -q` AND as a plain `python test_reporter_flywheel.py`
because conformance CI runs behavior proofs as plain scripts, with no pytest.
"""
import hashlib
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from emet import report, witness_receipt  # noqa: E402
from emet.reporters import flywheel as fw  # noqa: E402

NOW = "2026-09-13T00:00:00Z"


def _bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _inspect_report():
    return {
        "schema": "flywheel.inspect-evidence/v1",
        "producer": {"format": "inspect-json", "version": 2},
        "reported_status": "success",
        "assessment": "reported",
        "semantic_verification": "UNVERIFIABLE",
        "invalidated": False,
        "counts": {"total_samples": 2, "completed_samples": 2},
        "source": {"sha256": "a" * 64, "byte_length": 123},
        "source_pointers": [
            {"json_pointer": "/private",
             "source_value": "C:/private/operator/log.json"}
        ],
        "does_not_prove": ["semantic truth"],
    }


def _incident_command(verdict="MATCH"):
    return {
        "schema": "flywheel.incident-sim-command/v1",
        "evaluation": {"overall": {"verdict": verdict}},
        "audit_packet": {
            "evaluation": {"overall": {"verdict": verdict}},
            "source_values": [
                {"json_pointer": "/final_state",
                 "source_value": "private-source-value"}
            ],
        },
        "sources": {
            "task": {"sha256": "b" * 64, "byte_length": 100},
            "trace": {"sha256": "c" * 64, "byte_length": 120},
        },
        "does_not_prove": ["semantic truth"],
    }



def _process_audit_packet(verdict="MATCH"):
    return {
        "schema": "flywheel.incident-sim-process-audit/v1",
        "task_sha256": "1" * 64,
        "trace_sha256": "2" * 64,
        "evaluation_sha256": "3" * 64,
        "packet_sha256": "4" * 64,
        "evaluation": {"overall": {"verdict": verdict}},
        "source_values": [
            {"source": "trace", "json_pointer": "/final_state", "source_value": "private-packet-value"}
        ],
        "independence": {
            "roles": {"producer": "fixture", "checker": "flywheel"},
            "shared_dependencies": ["harness.incident_sim_eval"],
            "unknowns": ["assessment independence is unknown"],
        },
        "receipt_verification": {"work": {"verdict": "MATCH"}},
        "receipts": {"work": {"seal": {"hex": "5" * 64}}, "actions": [], "audit": {}},
        "receipt_limitations": ["Action receipts are reconstructed from a submitted trace"],
        "integration_limits": ["No live agent execution"],
    }


def test_process_audit_packet_receipt_returns_reviewer_commitment():
    raw = _bytes(_process_audit_packet("MATCH"))

    receipt, artifacts, commitment = fw.mint_packet_receipt(raw, now=NOW)

    assert set(artifacts) == {fw.PACKET_FILENAME, fw.PACKET_RECORD_FILENAME}
    assert artifacts[fw.PACKET_FILENAME] == raw
    assert receipt["verdict_record"] == []
    assert [row["path"] for row in receipt["subject"]] == [
        fw.PACKET_FILENAME, fw.PACKET_RECORD_FILENAME]
    assert commitment["schema"] == "emet-flywheel-packet-commitment/v2"
    assert commitment["packet_sha256"] == hashlib.sha256(raw).hexdigest()
    assert commitment["receipt_id"] == receipt["receipt_id"]
    assert commitment["receipt_sha256"] == hashlib.sha256(
        report.canonical(receipt).encode("utf-8")).hexdigest()
    assert commitment["separate_retention_required"] is True
    assert commitment["scope"] and "does_not_prove" not in commitment
    record = json.loads(artifacts[fw.PACKET_RECORD_FILENAME].decode("utf-8"))
    assert record["producer_schema"] == "flywheel.incident-sim-process-audit/v1"
    assert record["producer_claims"] == {"evaluation_overall_verdict": "MATCH"}
    assert b"private-packet-value" not in artifacts[fw.PACKET_RECORD_FILENAME]


def test_process_audit_changed_rebuilt_reminted_witness_and_missing_controls():
    raw = _bytes(_process_audit_packet("MATCH"))
    rebuilt = _bytes(_process_audit_packet("DRIFT"))

    with tempfile.TemporaryDirectory(prefix="emet_fw_packet_") as tmp:
        receipt, artifacts, commitment = fw.mint_packet_receipt(raw, now=NOW)
        _write_artifacts(tmp, artifacts)
        assert witness_receipt.check_receipt(receipt, base_dir=tmp, recompute=True)[0] == "RECEIPT_VALID"

        with open(os.path.join(tmp, fw.PACKET_FILENAME), "ab") as handle:
            handle.write(b"\n")
        assert witness_receipt.check_receipt(receipt, base_dir=tmp, recompute=True)[0] == "RECEIPT_TAMPERED"

    with tempfile.TemporaryDirectory(prefix="emet_fw_packet_") as tmp:
        receipt, artifacts, commitment = fw.mint_packet_receipt(raw, now=NOW)
        _write_artifacts(tmp, artifacts)
        with open(os.path.join(tmp, fw.PACKET_FILENAME), "wb") as handle:
            handle.write(rebuilt)
        assert witness_receipt.check_receipt(receipt, base_dir=tmp, recompute=True)[0] == "RECEIPT_TAMPERED"

    reminted_receipt, _reminted_artifacts, reminted_commitment = fw.mint_packet_receipt(rebuilt, now=NOW)
    assert witness_receipt.check_receipt(reminted_receipt)[0] == "RECEIPT_VALID"
    assert reminted_commitment["receipt_sha256"] != commitment["receipt_sha256"]
    assert reminted_commitment["receipt_id"] != commitment["receipt_id"]

    substituted = json.loads(report.canonical(receipt))
    substituted["witness"] = dict(substituted["witness"])
    substituted["witness"]["implementation"] = "substituted"
    assert witness_receipt.check_receipt(substituted)[0] == "RECEIPT_VALID"
    assert hashlib.sha256(report.canonical(substituted).encode("utf-8")).hexdigest() != commitment["receipt_sha256"]

    with tempfile.TemporaryDirectory(prefix="emet_fw_packet_") as tmp:
        _write_artifacts(tmp, {fw.PACKET_RECORD_FILENAME: artifacts[fw.PACKET_RECORD_FILENAME]})
        assert witness_receipt.check_receipt(receipt, base_dir=tmp, recompute=True)[0] == "RECEIPT_UNVERIFIABLE"


def test_write_packet_artifacts_refuses_to_clobber_existing_outputs():
    raw = _bytes(_process_audit_packet("MATCH"))
    receipt, artifacts, commitment = fw.mint_packet_receipt(raw, now=NOW)

    with tempfile.TemporaryDirectory(prefix="emet_fw_packet_") as tmp:
        written = fw.write_packet_artifacts(tmp, receipt, artifacts, commitment)
        assert os.path.exists(written[fw.PACKET_FILENAME])
        assert os.path.exists(written[fw.PACKET_RECEIPT_FILENAME])
        assert os.path.exists(written[fw.PACKET_COMMITMENT_FILENAME])
        try:
            fw.write_packet_artifacts(tmp, receipt, artifacts, commitment)
        except FileExistsError:
            pass
        else:
            raise AssertionError("existing packet outputs should not be overwritten")


def test_write_packet_artifacts_rejects_non_fixed_names_before_mkdir():
    raw = _bytes(_process_audit_packet("MATCH"))
    receipt, artifacts, commitment = fw.mint_packet_receipt(raw, now=NOW)

    with tempfile.TemporaryDirectory(prefix="emet_fw_packet_") as tmp:
        out_dir = os.path.join(tmp, "out")
        bad = dict(artifacts)
        bad["../escape.json"] = b"escape"
        try:
            fw.write_packet_artifacts(out_dir, receipt, bad, commitment)
        except ValueError as exc:
            assert str(exc).startswith("E_ARTIFACT_KEYS")
        else:
            raise AssertionError("writer should reject traversal artifact names")
        assert not os.path.exists(out_dir)
        assert not os.path.exists(os.path.join(tmp, "escape.json"))

    with tempfile.TemporaryDirectory(prefix="emet_fw_packet_") as tmp:
        out_dir = os.path.join(tmp, "out")
        absolute_name = os.path.join(tmp, "absolute.json")
        bad = dict(artifacts)
        bad[absolute_name] = b"absolute"
        try:
            fw.write_packet_artifacts(out_dir, receipt, bad, commitment)
        except ValueError as exc:
            assert str(exc).startswith("E_ARTIFACT_KEYS")
        else:
            raise AssertionError("writer should reject absolute artifact names")
        assert not os.path.exists(out_dir)
        assert not os.path.exists(absolute_name)


def test_write_packet_artifacts_rejects_non_bytes_before_mkdir():
    raw = _bytes(_process_audit_packet("MATCH"))
    receipt, artifacts, commitment = fw.mint_packet_receipt(raw, now=NOW)

    with tempfile.TemporaryDirectory(prefix="emet_fw_packet_") as tmp:
        out_dir = os.path.join(tmp, "out")
        bad = dict(artifacts)
        bad[fw.PACKET_RECORD_FILENAME] = "not bytes"
        try:
            fw.write_packet_artifacts(out_dir, receipt, bad, commitment)
        except ValueError as exc:
            assert str(exc).startswith("E_ARTIFACT_BYTES")
        else:
            raise AssertionError("writer should reject non-byte artifact values")
        assert not os.path.exists(out_dir)


def test_write_packet_artifacts_refuses_dangling_output_symlink():
    raw = _bytes(_process_audit_packet("MATCH"))
    receipt, artifacts, commitment = fw.mint_packet_receipt(raw, now=NOW)

    with tempfile.TemporaryDirectory(prefix="emet_fw_packet_") as tmp:
        out_dir = os.path.join(tmp, "out")
        os.makedirs(out_dir)
        target = os.path.join(out_dir, fw.PACKET_COMMITMENT_FILENAME)
        try:
            os.symlink(os.path.join(out_dir, "missing-target"), target)
        except (OSError, NotImplementedError):
            return

        try:
            fw.write_packet_artifacts(out_dir, receipt, artifacts, commitment)
        except FileExistsError:
            pass
        else:
            raise AssertionError("writer should reject dangling output links")
        assert os.path.islink(target)


def test_write_packet_artifacts_does_not_overwrite_raced_output():
    raw = _bytes(_process_audit_packet("MATCH"))
    receipt, artifacts, commitment = fw.mint_packet_receipt(raw, now=NOW)

    with tempfile.TemporaryDirectory(prefix="emet_fw_packet_") as tmp:
        out_dir = os.path.join(tmp, "out")
        raced = os.path.join(out_dir, fw.PACKET_RECORD_FILENAME)
        original_exists = fw.os.path.exists
        original_lexists = getattr(fw.os.path, "lexists", original_exists)
        state = {"armed": True}

        def race_once(path):
            if path == raced and state["armed"]:
                state["armed"] = False
                os.makedirs(out_dir, exist_ok=True)
                with open(raced, "wb") as handle:
                    handle.write(b"raced")
                return False
            return original_lexists(path)

        fw.os.path.exists = race_once
        fw.os.path.lexists = race_once
        try:
            try:
                fw.write_packet_artifacts(out_dir, receipt, artifacts, commitment)
            except FileExistsError:
                pass
            else:
                raise AssertionError("writer should fail when output appears during write")
        finally:
            fw.os.path.exists = original_exists
            fw.os.path.lexists = original_lexists

        with open(raced, "rb") as handle:
            assert handle.read() == b"raced"


def test_packet_api_rejects_wrong_schema_and_malformed_packet_shape():
    try:
        fw.mint_packet_receipt(_bytes(_incident_command("MATCH")), now=NOW)
    except ValueError as exc:
        assert str(exc).startswith("E_SCHEMA")
    else:
        raise AssertionError("packet API should require process-audit schema")

    doc = _process_audit_packet("MATCH")
    del doc["receipts"]
    try:
        fw.mint_packet_receipt(_bytes(doc), now=NOW)
    except ValueError as exc:
        assert str(exc).startswith("E_SHAPE")
    else:
        raise AssertionError("packet API should reject malformed packet shape")

    try:
        fw.mint_packet_receipt(b" " * (16 * 1024 * 1024 + 1), now=NOW)
    except ValueError as exc:
        assert str(exc).startswith("E_TOO_LARGE")
    else:
        raise AssertionError("packet API should reject oversized packet bytes")


def _write_artifacts(directory, artifacts):
    for name, data in artifacts.items():
        with open(os.path.join(directory, name), "wb") as handle:
            handle.write(data)


def _assert_error(raw, prefix):
    try:
        fw.build_eval_record(raw)
    except ValueError as exc:
        assert str(exc).startswith(prefix)
    else:
        raise AssertionError(prefix + " expected")


def test_inspect_record_is_bounded_projection_without_raw_source_values():
    raw = _bytes(_inspect_report())

    record = fw.build_eval_record(raw)
    record_bytes = report.canonical(record).encode("utf-8")

    assert record["schema"] == "emet-flywheel-evaluation-record/v2"
    assert record["producer_schema"] == "flywheel.inspect-evidence/v1"
    assert record["source"] == {
        "algorithm": "sha256",
        "byte_length": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    assert record["producer_claims"] == {
        "reported_status": "success",
        "assessment": "reported",
        "semantic_verification": "UNVERIFIABLE",
        "invalidated": "false",
    }
    assert record["semantic_conclusions_verified_by_emet"] == "UNVERIFIED"
    assert b"C:/private" not in record_bytes


def test_inspect_input_reads_scope_or_the_older_does_not_prove_name():
    newer = _inspect_report()
    newer["scope"] = newer.pop("does_not_prove")
    older = _inspect_report()
    claims_newer = fw.build_eval_record(_bytes(newer))["producer_claims"]
    claims_older = fw.build_eval_record(_bytes(older))["producer_claims"]
    assert claims_newer == claims_older
    record = fw.build_eval_record(_bytes(older))
    assert record["scope"] and "does_not_prove" not in record


def test_mint_receipt_addresses_raw_and_metadata_and_recomputes_valid():
    raw = _bytes(_inspect_report())

    with tempfile.TemporaryDirectory(prefix="emet_fw_") as tmp:
        receipt, artifacts = fw.mint_receipt(raw, now=NOW)
        _write_artifacts(tmp, artifacts)

        assert set(artifacts) == {fw.RAW_REPORT_FILENAME, fw.RECORD_FILENAME}
        assert artifacts[fw.RAW_REPORT_FILENAME] == raw
        assert receipt["verdict_record"] == []
        assert [row["path"] for row in receipt["subject"]] == [
            fw.RAW_REPORT_FILENAME, fw.RECORD_FILENAME]
        verdict, _ = witness_receipt.check_receipt(receipt, base_dir=tmp)
        assert verdict == "RECEIPT_VALID"
        verdict2, _ = witness_receipt.check_receipt(
            receipt, base_dir=tmp, recompute=True)
        assert verdict2 == "RECEIPT_VALID"


def test_changed_raw_artifact_tampers_and_missing_artifact_is_unverifiable():
    raw = _bytes(_inspect_report())

    with tempfile.TemporaryDirectory(prefix="emet_fw_") as tmp:
        receipt, artifacts = fw.mint_receipt(raw, now=NOW)
        _write_artifacts(tmp, artifacts)

        with open(os.path.join(tmp, fw.RAW_REPORT_FILENAME), "ab") as handle:
            handle.write(b"\n")
        verdict, _ = witness_receipt.check_receipt(
            receipt, base_dir=tmp, recompute=True)
        assert verdict == "RECEIPT_TAMPERED"

        _write_artifacts(tmp, artifacts)
        os.unlink(os.path.join(tmp, fw.RECORD_FILENAME))
        verdict2, _ = witness_receipt.check_receipt(
            receipt, base_dir=tmp, recompute=True)
        assert verdict2 == "RECEIPT_UNVERIFIABLE"


def test_wrong_state_drift_can_still_have_intact_integrity_witness():
    raw = _bytes(_incident_command("DRIFT"))

    with tempfile.TemporaryDirectory(prefix="emet_fw_") as tmp:
        receipt, artifacts = fw.mint_receipt(raw, now=NOW)
        _write_artifacts(tmp, artifacts)
        record = json.loads(artifacts[fw.RECORD_FILENAME].decode("utf-8"))

        assert record["producer_claims"] == {
            "evaluation_overall_verdict": "DRIFT"
        }
        assert record["semantic_conclusions_verified_by_emet"] == "UNVERIFIED"
        assert receipt["verdict_record"] == []
        verdict, _ = witness_receipt.check_receipt(
            receipt, base_dir=tmp, recompute=True)
        assert verdict == "RECEIPT_VALID"


def test_malformed_or_oversize_inputs_fail_boundedly():
    cases = [
        ("duplicate-key",
         b'{"schema":"flywheel.inspect-evidence/v1","schema":"x"}'),
        ("nonfinite",
         b'{"schema":"flywheel.inspect-evidence/v1","reported_status":NaN}'),
        ("unknown-schema", b'{"schema":"unknown"}'),
        ("too-deep", b'[' + (b'[' * 40) + (b']' * 40) + b']'),
        ("too-large", b' ' * (16 * 1024 * 1024 + 1)),
    ]
    for name, raw in cases:
        try:
            fw.build_eval_record(raw)
        except ValueError as exc:
            assert str(exc).startswith("E_"), name
        else:
            raise AssertionError(name + " should raise ValueError")


def test_unknown_producer_claims_are_rejected_not_projected():
    for field in ("reported_status", "assessment", "semantic_verification"):
        doc = _inspect_report()
        doc[field] = "private-source-value"
        _assert_error(_bytes(doc), "E_ENUM")

    _assert_error(_bytes(_incident_command("private-source-value")), "E_ENUM")


def test_non_string_schema_values_raise_bounded_schema_error():
    _assert_error(_bytes({"schema": []}), "E_SCHEMA")
    _assert_error(_bytes({"schema": {}}), "E_SCHEMA")


def test_large_exponent_number_is_rejected_before_projection():
    raw = (
        b'{"assessment":"reported","counts":{"bad":1e999},'
        b'"does_not_prove":[],"invalidated":false,'
        b'"producer":{},"reported_status":"success",'
        b'"schema":"flywheel.inspect-evidence/v1",'
        b'"semantic_verification":"UNVERIFIABLE",'
        b'"source":{},"source_pointers":[]}'
    )

    _assert_error(raw, "E_NONFINITE_NUMBER")


def test_receipt_and_metadata_do_not_copy_private_source_values():
    raw = _bytes(_incident_command("MATCH"))

    receipt, artifacts = fw.mint_receipt(raw, now=NOW)
    public_bytes = (
        report.canonical(receipt).encode("utf-8") + artifacts[fw.RECORD_FILENAME]
    )

    assert b"private-source-value" not in public_bytes


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("PASS " + fn.__name__)
    print("OK " + str(len(fns)) + " flywheel-reporter behavior proofs")


if __name__ == "__main__":
    _run_all()
