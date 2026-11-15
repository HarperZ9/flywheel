#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
import hashlib
import json
import os

from adapters.proof_surface_receipt import bundle_receipt


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _write_bundle(tmp_path, files, schema="proof-surface-bundle/v0"):
    # files: list of (name, on_disk_bytes, recorded_bytes_or_None).
    # recorded digest is computed from recorded_bytes; on_disk is what we write.
    entries = []
    for name, on_disk, recorded in files:
        if on_disk is not None:
            with open(os.path.join(tmp_path, name), "wb") as handle:
                handle.write(on_disk)
        digest_source = recorded if recorded is not None else on_disk
        entries.append({"name": name, "sha256": _sha256_bytes(digest_source)})
    manifest = {
        "schema": schema,
        "domain": "test-domain",
        "packet_id": "packet-0001",
        "bundle_hash": "0" * 64,
        "files": entries,
    }
    bundle_path = os.path.join(tmp_path, "bundle.json")
    with open(bundle_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle)
    return bundle_path


def test_bundle_all_files_match(tmp_path):
    tmp = str(tmp_path)
    packet = b'{"packet":"body"}'
    report = b"# report\nmeasured\n"
    bundle_path = _write_bundle(
        tmp,
        [("packet.json", packet, None), ("report.md", report, None)],
    )

    data = bundle_receipt(bundle_path)

    assert data["verdict"] == "MATCH"
    assert data["witness"]["check"] == "bundle"
    assert data["evidence"]["files_total"] == 2
    assert data["evidence"]["files_rederived"] == 2
    encoded = json.dumps(data)
    assert "TRUSTED" not in encoded


def test_bundle_tampered_sibling_is_drift(tmp_path):
    tmp = str(tmp_path)
    # report.md recorded from clean bytes but tampered bytes on disk.
    bundle_path = _write_bundle(
        tmp,
        [
            ("packet.json", b'{"packet":"body"}', None),
            ("report.md", b"TAMPERED\n", b"# report\nmeasured\n"),
        ],
    )

    data = bundle_receipt(bundle_path)

    assert data["verdict"] == "DRIFT"
    assert data["evidence"]["files_rederived"] == 1
    assert "report.md" in data["evidence"]["stdout_verdict_line"]


def test_bundle_missing_sibling_is_unverifiable(tmp_path):
    tmp = str(tmp_path)
    # report.md listed but not written to disk (on_disk None).
    bundle_path = _write_bundle(
        tmp,
        [
            ("packet.json", b'{"packet":"body"}', None),
            ("report.md", None, b"# report\nmeasured\n"),
        ],
    )

    data = bundle_receipt(bundle_path)

    assert data["verdict"] == "UNVERIFIABLE"
    assert "report.md" in data["evidence"]["stdout_verdict_line"]


def test_bundle_malformed_json_is_unverifiable(tmp_path):
    tmp = str(tmp_path)
    bundle_path = os.path.join(tmp, "bundle.json")
    with open(bundle_path, "w", encoding="utf-8") as handle:
        handle.write("{not valid json")

    data = bundle_receipt(bundle_path)

    assert data["verdict"] == "UNVERIFIABLE"


def test_bundle_missing_bundle_file_is_unverifiable(tmp_path):
    tmp = str(tmp_path)
    bundle_path = os.path.join(tmp, "does-not-exist.json")

    data = bundle_receipt(bundle_path)

    assert data["verdict"] == "UNVERIFIABLE"


def test_bundle_wrong_schema_is_unverifiable(tmp_path):
    tmp = str(tmp_path)
    bundle_path = _write_bundle(
        tmp,
        [("packet.json", b'{"packet":"body"}', None)],
        schema="some-other-schema/v9",
    )

    data = bundle_receipt(bundle_path)

    assert data["verdict"] == "UNVERIFIABLE"


def test_bundle_refuses_injected_authority_token(tmp_path):
    tmp = str(tmp_path)
    # An authority token injected as a manifest file name. If it ever reached
    # a MATCH verdict line it would leak; the adapter must refuse it and never
    # emit an authority token, keeping the verdict inside the closed lattice.
    with open(os.path.join(tmp, "packet.json"), "wb") as handle:
        handle.write(b'{"packet":"body"}')
    with open(os.path.join(tmp, "TRUSTED.md"), "wb") as handle:
        handle.write(b"payload\n")
    manifest = {
        "schema": "proof-surface-bundle/v0",
        "domain": "test-domain",
        "packet_id": "packet-0001",
        "bundle_hash": "0" * 64,
        "files": [
            {"name": "packet.json", "sha256": _sha256_bytes(b'{"packet":"body"}')},
            {"name": "TRUSTED.md", "sha256": _sha256_bytes(b"payload\n")},
        ],
    }
    bundle_path = os.path.join(tmp, "bundle.json")
    with open(bundle_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle)

    data = bundle_receipt(bundle_path)

    assert data["verdict"] == "UNVERIFIABLE"
    assert data["verdict"] != "TRUSTED"
    encoded = json.dumps(data)
    assert '"verdict": "TRUSTED"' not in encoded
