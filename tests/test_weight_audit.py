"""Tests for harness.weight_audit (I13 local binary & weight-manifest integrity scanner)."""

from __future__ import annotations

import copy
import re
from pathlib import Path

from harness.weight_audit import (
    audit_artifact_root,
    build_weight_manifest,
    scan_static_outbound_and_telemetry,
)


def _seed_clean_container(root: Path) -> None:
    (root / "weights").mkdir(parents=True, exist_ok=True)
    (root / "weights" / "model.safetensors").write_bytes(b"\x01\x02SAFEWEIGHTS" * 64)
    (root / "weights" / "quant.gguf").write_bytes(b"GGUF\x03\x00\x00\x00" + b"\xaa" * 128)
    (root / "runtime.py").write_text(
        "import socket\n"
        "def local_ping():\n"
        "    return socket.create_connection(('127.0.0.1', 8080))\n",
        encoding="utf-8",
    )
    (root / "config.json").write_text('{"bind": "http://127.0.0.1:8080"}\n', encoding="utf-8")


def test_clean_manifest_and_loopback_runtime_pass(tmp_path: Path) -> None:
    _seed_clean_container(tmp_path)
    manifest = build_weight_manifest(tmp_path)
    assert manifest["file_count"] == 2
    assert manifest["merkle_root"].startswith("sha256:")

    report = audit_artifact_root(tmp_path, manifest)
    assert report["ok"] is True
    assert report["verdict"] == "PASS"
    assert report["weights_and_binaries_checked"] == 2
    assert report["findings"] == []
    assert report["report_sha256"].startswith("sha256:")


def test_planted_unhashed_weight_blob_and_one_byte_tamper_caught(tmp_path: Path) -> None:
    _seed_clean_container(tmp_path)

    # 1. No manifest at all -> every weight blob fails closed as UNHASHED_WEIGHT_OR_BINARY
    no_man = audit_artifact_root(tmp_path, manifest=None)
    assert not no_man["ok"] and no_man["finding_counts"]["UNHASHED_WEIGHT_OR_BINARY"] == 2

    manifest = build_weight_manifest(tmp_path)

    # 2. Plant an extra unlisted weight blob
    hidden = tmp_path / "weights" / "hidden_adapter.bin"
    hidden.write_bytes(b"HIDDEN_WEIGHTS_BLOB")
    rep_unlisted = audit_artifact_root(tmp_path, manifest)
    assert not rep_unlisted["ok"]
    assert rep_unlisted["finding_counts"]["UNHASHED_WEIGHT_OR_BINARY"] == 1
    hidden.unlink()

    # 3. Plant a 1-byte mutation in a listed weight file
    sf = tmp_path / "weights" / "model.safetensors"
    orig = sf.read_bytes()
    sf.write_bytes(bytes([orig[0] ^ 0xFF]) + orig[1:])
    rep_tamper = audit_artifact_root(tmp_path, manifest)
    assert not rep_tamper["ok"]
    assert rep_tamper["finding_counts"]["TAMPERED_WEIGHT_OR_BINARY"] == 1
    sf.write_bytes(orig)

    # 4. Plant a tampered manifest Merkle root
    bad_man = copy.deepcopy(manifest)
    bad_man["entries"][0]["size_bytes"] = 999999
    rep_man = audit_artifact_root(tmp_path, bad_man)
    assert not rep_man["ok"]
    assert rep_man["finding_counts"]["MANIFEST_MERKLE_TAMPER"] == 1


def test_planted_outbound_socket_telemetry_and_locked_firmware_caught(tmp_path: Path) -> None:
    _seed_clean_container(tmp_path)
    manifest = build_weight_manifest(tmp_path)

    (tmp_path / "exfil.py").write_text(
        "import socket\n"
        "import posthog\n"
        "import urllib.request\n"
        "def beacon():\n"
        "    socket.create_connection(('telemetry.vendor.example', 443))\n"
        "    urllib.request.urlopen('https://collect.vendor.example/ping')\n",
        encoding="utf-8",
    )
    (tmp_path / "start.sh").write_text(
        "#!/bin/sh\n"
        "curl -s https://phonehome.vendor.example/boot\n"
        "echo locked_firmware=true\n",
        encoding="utf-8",
    )

    report = audit_artifact_root(tmp_path, manifest)
    assert not report["ok"] and report["verdict"] == "FAIL"
    codes = set(report["finding_counts"])
    assert "UNAUTHORIZED_OUTBOUND_SOCKET" in codes
    assert "UNDOCUMENTED_TELEMETRY" in codes
    assert "UNDOCUMENTED_OUTBOUND_URL" in codes
    assert "LOCKED_FIRMWARE_OR_AUDIT_BYPASS" in codes


def test_operator_allowlisted_host_is_permitted(tmp_path: Path) -> None:
    (tmp_path / "client.py").write_text(
        "import urllib.request\n"
        "def fetch_mirror():\n"
        "    return urllib.request.urlopen('https://mirror.local.internal/model.json')\n",
        encoding="utf-8",
    )
    blocked = scan_static_outbound_and_telemetry(tmp_path)
    assert any(f["code"] == "UNAUTHORIZED_OUTBOUND_SOCKET" for f in blocked)

    allowed = scan_static_outbound_and_telemetry(tmp_path, allow_hosts=["mirror.local.internal"])
    assert allowed == []


def test_remedy_and_weight_audit_line_budgets_and_hygiene() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    files = [
        repo_root / "harness" / "remedy.py",
        repo_root / "harness" / "weight_audit.py",
        repo_root / "tests" / "test_remedy.py",
        Path(__file__).resolve(),
    ]
    local_path_re = re.compile(r"[A-Za-z]:\\(?:dev|Users)\\")
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert len(text.splitlines()) <= 300, f"{path.name} exceeds 300-line gate"
        assert "\u2014" not in text, f"{path.name} contains a literal em dash"
        assert not local_path_re.search(text), f"{path.name} contains a hardcoded local path"
