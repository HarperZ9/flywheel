# SPDX-License-Identifier: MIT
"""Unit and adversarial tamper tests for harness.sbom_gate."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

from harness import sbom_gate as sg


def _make_spdx(name: str = "demo-repo", lic: str = "MIT") -> dict:
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": name,
        "documentNamespace": f"https://example.org/spdx/{name}",
        "creationInfo": {"creators": ["Tool: sbom-gate-test"], "created": "2026-11-27T00:00:00Z"},
        "packages": [
            {"name": name, "SPDXID": "SPDXRef-Root", "licenseConcluded": lic},
            {"name": "dep-a", "SPDXID": "SPDXRef-DepA", "licenseConcluded": "Apache-2.0 OR MIT"},
        ],
        "relationships": [{"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": "SPDXRef-Root"}],
    }


def _make_cdx(name: str = "demo-repo", lic: str = "MIT") -> dict:
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": "urn:uuid:11111111-2222-4333-8444-555555555555",
        "version": 1,
        "metadata": {"component": {"type": "application", "name": name, "bom-ref": name}},
        "components": [
            {"type": "library", "name": "dep-a", "version": "1.0.0", "licenses": [{"license": {"id": lic}}]},
            {"type": "library", "name": "dep-b", "version": "2.0.0", "licenses": [{"expression": "MIT OR Apache-2.0"}]},
        ],
        "dependencies": [{"ref": name, "dependsOn": ["dep-a", "dep-b"]}],
    }


def test_spdx_valid_document_passes() -> None:
    rep = sg.verify_spdx_doc(_make_spdx())
    assert rep.passed is True and rep.package_count == 2 and rep.reasons == ()
    assert rep.to_dict()["passed"] is True


def test_spdx_missing_headers_fail_closed() -> None:
    doc = _make_spdx()
    for key in ("spdxVersion", "dataLicense", "SPDXID", "documentNamespace", "creationInfo", "relationships"):
        doc.pop(key)
    rep = sg.verify_spdx_doc(doc)
    assert rep.passed is False
    assert {"INVALID_DATA_LICENSE", "MISSING_SPDXREF_DOCUMENT", "MISSING_DOCUMENT_NAMESPACE",
            "MISSING_CREATION_INFO", "MISSING_RELATIONSHIPS"} <= set(rep.reasons)


def test_cyclonedx_valid_document_passes() -> None:
    rep = sg.verify_cyclonedx_doc(_make_cdx())
    assert rep.passed is True and rep.component_count == 2 and rep.reasons == ()
    assert rep.to_dict()["passed"] is True


def test_cyclonedx_missing_headers_fail_closed() -> None:
    doc = _make_cdx()
    for key in ("bomFormat", "specVersion", "serialNumber", "metadata", "dependencies"):
        doc.pop(key)
    doc["components"] = []
    rep = sg.verify_cyclonedx_doc(doc)
    assert rep.passed is False
    assert {"INVALID_OR_MISSING_BOM_FORMAT", "INVALID_SERIAL_NUMBER", "MISSING_METADATA_COMPONENT",
            "MISSING_DEPENDENCIES", "INSUFFICIENT_CYCLONEDX_COMPONENTS"} <= set(rep.reasons)


@pytest.mark.parametrize("bad_lic", ["SSPL-1.0", "BSL-1.1", "BUSL-1.1", "UNLICENSED", "ALL-RIGHTS-RESERVED"])
def test_forbidden_license_tokens_rejected_in_both_formats(bad_lic: str) -> None:
    sp = sg.verify_spdx_doc(_make_spdx(lic=bad_lic))
    cdx = sg.verify_cyclonedx_doc(_make_cdx(lic=bad_lic))
    assert sp.passed is False and f"FORBIDDEN_LICENSE:{bad_lic}" in sp.reasons
    assert cdx.passed is False and f"FORBIDDEN_LICENSE:{bad_lic}" in cdx.reasons


def test_license_expression_grammar_and_allowlist() -> None:
    assert sg.is_valid_spdx_expression("(MIT OR Apache-2.0) AND BSD-3-Clause") is True
    assert sg.is_valid_spdx_expression("(MIT OR Apache-2.0") is False
    assert sg.is_valid_spdx_expression("not valid license!!") is False
    rep = sg.verify_cyclonedx_doc(_make_cdx(lic="GPL-3.0-only"), allowed_licenses={"MIT", "Apache-2.0"})
    assert rep.passed is False and "UNAPPROVED_LICENSE:GPL-3.0-only" in rep.reasons


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        (chr(67) + ":" + chr(92) + "Us" + "ers" + chr(92) + "alice" + chr(92) + "repo", "LOCAL_WINDOWS_PATH_LEAK"),
        ("/ho" + "me/alice/src/repo", "LOCAL_POSIX_PATH_LEAK"),
        ("alice" + chr(64) + "example.org", "EMAIL_PII_LEAK"),
        ("AK" + "IA0123456789ABCDEF", "AWS_KEY_LEAK"),
        ("gh" + "p_" + ("A" * 24), "GITHUB_TOKEN_LEAK"),
        ("-----BEGIN RSA PRIVATE" + " KEY-----", "PRIVATE_KEY_LEAK"),
    ],
)
def test_zero_pii_and_local_path_leak_scanner_fails_closed(payload: str, expected_code: str) -> None:
    doc = _make_cdx()
    doc["metadata"]["component"]["name"] = payload
    rep = sg.verify_cyclonedx_doc(doc)
    assert rep.passed is False and expected_code in rep.reasons
    sp = _make_spdx()
    sp["name"] = payload
    rep_sp = sg.verify_spdx_doc(sp)
    assert rep_sp.passed is False and expected_code in rep_sp.reasons


def test_supply_chain_gate_passes_pack_and_seals_deterministic_sha256(tmp_path: Path) -> None:
    (tmp_path / "spdx").mkdir()
    (tmp_path / "cyclonedx").mkdir()
    (tmp_path / "spdx" / "a.spdx.json").write_text(json.dumps(_make_spdx("a")), encoding="utf-8")
    (tmp_path / "cyclonedx" / "a.cdx.json").write_text(json.dumps(_make_cdx("a")), encoding="utf-8")
    (tmp_path / "harper-stack-5flagships.cdx.json").write_text(json.dumps(_make_cdx("unified")), encoding="utf-8")

    rep = sg.verify_sbom_pack(tmp_path, expected_sbom_count=3)
    assert rep.passed is True and rep.sboms_checked == 3 and rep.sboms_passed == 3
    assert rep.spdx_count == 1 and rep.cyclonedx_count == 2 and rep.unified_components == 2
    assert len(rep.sbom_attestation_sha256) == 64
    assert rep.sbom_attestation_sha256 == sg.verify_sbom_pack(tmp_path).sbom_attestation_sha256
    assert rep.to_dict()["passed"] is True


def test_supply_chain_gate_catches_missing_dir_empty_count_and_bad_json(tmp_path: Path) -> None:
    assert "MISSING_PACK_DIR" in sg.verify_sbom_pack(tmp_path / "missing").reasons
    assert "EMPTY_SBOM_PACK" in sg.verify_sbom_pack(tmp_path).reasons
    (tmp_path / "broken.spdx.json").write_text("{bad", encoding="utf-8")
    rep = sg.verify_sbom_pack(tmp_path, expected_sbom_count=2)
    assert rep.passed is False
    assert "SBOM_COUNT_MISMATCH:1!=2" in rep.reasons
    assert "broken.spdx.json:INVALID_SPDX_JSON" in rep.reasons


def test_file_helpers_handle_missing_files(tmp_path: Path) -> None:
    assert "MISSING_SPDX_FILE" in sg.verify_spdx_file(tmp_path / "no.spdx.json").reasons
    assert "MISSING_CYCLONEDX_FILE" in sg.verify_cyclonedx_file(tmp_path / "no.cdx.json").reasons


@pytest.mark.parametrize(
    ("expr", "expected_tokens"),
    [
        ("MIT", ["MIT"]),
        ("Apache-2.0 OR MIT", ["Apache-2.0", "MIT"]),
        ("(MIT OR Apache-2.0) AND ISC", ["MIT", "Apache-2.0", "ISC"]),
        ("NOASSERTION", ["NOASSERTION"]),
        ("LicenseRef-FSL-1.1-MIT", ["LicenseRef-FSL-1.1-MIT"]),
        ("CC0-1.0", ["CC0-1.0"]),
    ],
)
def test_spdx_expression_token_extraction(expr: str, expected_tokens: list[str]) -> None:
    assert sg.is_valid_spdx_expression(expr) is True
    assert sg.extract_license_tokens(expr) == expected_tokens


def test_package_hygiene_loc_spdx_stdlib_and_scope_limits() -> None:
    root = Path(__file__).resolve().parents[1]
    pkg_files = sorted((root / "harness" / "sbom_gate").glob("*.py"))
    assert len(pkg_files) == 4
    assert set(sg.HONEST_SCOPE_LIMITS) == {"spdx_check", "cyclonedx_check", "supply_chain_gate"}
    for path in [*pkg_files, Path(__file__).resolve()]:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        assert len(lines) <= 250, f"{path.name} has {len(lines)} lines (> 250)"
        assert lines[0] == "# SPDX-License-Identifier: MIT"
        assert "\u2014" not in text and "\u2013" not in text
    for path in pkg_files:
        text = path.read_text(encoding="utf-8")
        assert "HONEST_SCOPE_LIMIT" in text
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Import):
                assert all(a.name.split(".")[0] in sys.stdlib_module_names for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                assert node.module.split(".")[0] in sys.stdlib_module_names
