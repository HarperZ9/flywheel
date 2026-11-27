# SPDX-License-Identifier: MIT
"""Unit, adversarial, and 400-trial fuzz tests for quic_firewall_attest and oss_gold_sbom_gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
from typing import Any

import pytest

from harness.oss_gold_sbom_gate import (
    GoldSbomV3Policy,
    parse_sbom_v3_manifest,
    verify_gold_sbom_v3_bundle,
    verify_gold_sbom_v3_file,
)
from harness.oss_gold_sbom_gate.sbom_v3_oracle import main as sbom_main
from harness.quic_firewall_attest import (
    QuicFirewallPolicy,
    REQUIRED_ISAS,
    REQUIRED_NET_ATTACKS,
    parse_quic_payload,
    parse_quic_receipt,
    verify_quic_firewall_bundle,
    verify_quic_firewall_file,
)
from harness.quic_firewall_attest.quic_oracle import main as quic_main


def _hex64(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _valid_quic_payload() -> dict[str, Any]:
    return {
        "schema": "quic-firewall-bundle/1",
        "verdict": "MATCH",
        "oracle_exit_code": 0,
        "claim_sha256": f"sha256:{_hex64('quic_claim')}",
        "quic_root_hex": _hex64("quic_root"),
        "tx_sha_hex": _hex64("tx_sha"),
        "fw_sha_hex": _hex64("fw_sha"),
        "cwnd": 5550,
        "ssthresh": 4950,
        "max_pn": 107,
        "bmp_lo": 255,
        "packet_numbers": [100, 101, 102, 103, 104, 105, 106, 107],
        "firewall_default": "DENY",
        "firewall_rules": [
            {"capability": "CAP_NET_PEER", "peer_id": "peer-alpha-01", "action": "ALLOW"},
            {"capability": "NONE", "peer_id": "untrusted-peer", "action": "DENY"},
        ],
        "binaries": [
            {"isa": isa, "rel_path": f"out/{isa}.bin", "bytes": 12839 if isa == "wasm" else 36864 + i * 500, "sha256": _hex64(isa)}
            for i, isa in enumerate(REQUIRED_ISAS)
        ],
        "attacks": [
            {"name": atk, "rejected": True, "committed": 0, "error_code": -101 - i * 100, "isas_rejected": 5}
            for i, atk in enumerate(REQUIRED_NET_ATTACKS)
        ],
    }


def _valid_sbom_v3_manifest(tmp_path: Path | None = None, num_repos: int = 15) -> dict[str, Any]:
    repos: list[dict[str, Any]] = []
    total_comps = 0
    for i in range(num_repos):
        slug = f"repo_{i:02d}"
        comps = 175 if i == 0 else (13 if i == 2 else 6)
        lic = "AGPL-3.0-only" if i in (0, 3) else ("CC-BY-4.0" if i == 4 else "MIT")
        spdx_rel = f"spdx/{slug}.spdx.json"
        cdx_rel = f"cyclonedx/{slug}.cdx.json"
        spdx_raw = json.dumps({"spdxVersion": "SPDX-2.3", "name": slug, "license": lic}).encode("utf-8")
        cdx_raw = json.dumps({"bomFormat": "CycloneDX", "specVersion": "1.5", "name": slug, "license": lic}).encode("utf-8")
        if tmp_path is not None:
            (tmp_path / "spdx").mkdir(parents=True, exist_ok=True)
            (tmp_path / "cyclonedx").mkdir(parents=True, exist_ok=True)
            (tmp_path / spdx_rel).write_bytes(spdx_raw)
            (tmp_path / cdx_rel).write_bytes(cdx_raw)
        repos.append({
            "slug": slug,
            "repo": f"org/{slug}",
            "commit_sha": _hex64(f"git:{slug}")[:40],
            "license": lic,
            "component_count": comps,
            "spdx_file": spdx_rel,
            "spdx_sha256": hashlib.sha256(spdx_raw).hexdigest(),
            "cdx_file": cdx_rel,
            "cdx_sha256": hashlib.sha256(cdx_raw).hexdigest(),
        })
        total_comps += comps
    return {
        "schema": "harper-15repo-post-merge-sbom-v3-manifest/1",
        "spdx_version": "SPDX-2.3",
        "cyclonedx_version": "1.5",
        "total_sbom_files": num_repos * 2,
        "total_repos_covered": num_repos,
        "total_components_15repos": total_comps,
        "gold_standard_score": "165/165",
        "gold_standard_perfect_repos": "15/15",
        "osi_policy_audit": {"stale_fsl_in_sboms": 0, "proprietary_in_sboms": 0, "copyleft_in_mit_repos": 0},
        "repositories": repos,
    }


def test_quic_firewall_happy_path_and_receipt_cli(tmp_path: Path) -> None:
    rep = verify_quic_firewall_bundle(parse_quic_payload(_valid_quic_payload()))
    assert rep.ok and rep.verdict == "PASS" and rep.attacks_verified == 4 and rep.total_attack_rejections == 20
    suffixes = {"x64-pe": ".exe", "x64-elf": ".x64.elf", "rv64-elf": ".rv64.elf", "aarch64-elf": ".aarch64.elf", "wasm": ".wasm"}
    arts = []
    for isa, suf in suffixes.items():
        fp = tmp_path / f"quic{suf}"
        raw = f"quic-{isa}".encode("utf-8")
        fp.write_bytes(raw)
        arts.append({"rel_path": fp.name, "bytes": len(raw), "sha256": f"sha256:{hashlib.sha256(raw).hexdigest()}"})
    excerpt = json.dumps({"cwnd": 5550, "ssthresh": 4950, "max_pn": 107, "bmp_lo": 255, "tx_sha_hex": _hex64("t"), "fw_sha_hex": _hex64("f"), "quic_root_hex": _hex64("r")})
    rec = {"schema": "engine-receipt/1", "verdict": "MATCH", "digests": {"claim_sha256": f"sha256:{_hex64('c')}"}, "oracle": {"exit_code": 0, "stdout_excerpt": excerpt}, "subject": {"artifacts": arts}}
    rp = tmp_path / "rec.json"
    rp.write_text(json.dumps(rec), encoding="utf-8")
    pol = QuicFirewallPolicy(require_4_attacks=False, require_firewall_rules=False, check_on_disk=True)
    assert verify_quic_firewall_file(rp, policy=pol, artifact_root=tmp_path).ok
    assert quic_main([str(rp), "--receipt-only", "--check-on-disk", "--artifact-root", str(tmp_path)]) == 0
    (tmp_path / "quic.wasm").write_bytes(b"tampered")
    assert quic_main([str(rp), "--receipt-only", "--check-on-disk", "--artifact-root", str(tmp_path)]) == 2


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (lambda d: d["packet_numbers"].append(105), "replay_packet_detected"),
        (lambda d: d["packet_numbers"].append(10), "pn_window_underflow"),
        (lambda d: d.update({"bmp_lo": 127}), "bmp_lo_mismatch"),
        (lambda d: d.update({"firewall_default": "ALLOW"}), "firewall_not_deny_by_default"),
        (lambda d: d["firewall_rules"][0].update({"peer_id": "*"}), "firewall_wildcard_peer_allow"),
        (lambda d: d["firewall_rules"][0].update({"capability": "CAP_ANY"}), "firewall_missing_cap_net_peer"),
        (lambda d: d["attacks"][0].update({"rejected": False}), "net_attack_not_rejected"),
        (lambda d: d["attacks"][1].update({"committed": 1}), "net_attack_committed_nonzero"),
        (lambda d: d["attacks"][2].update({"isas_rejected": 4}), "net_attack_isa_count_low"),
        (lambda d: d["attacks"].pop(), "missing_net_attack"),
        (lambda d: d["binaries"].pop(), "missing_isa:wasm"),
        (lambda d: d.update({"verdict": "DRIFT"}), "invalid_verdict"),
    ],
)
def test_quic_firewall_planted_attacks_fail_closed(mutator: Any, expected: str) -> None:
    payload = _valid_quic_payload()
    mutator(payload)
    rep = verify_quic_firewall_bundle(parse_quic_payload(payload))
    assert not rep.ok and rep.verdict == "REJECT"
    assert any(expected in e for e in rep.errors), rep.errors


def test_oss_gold_sbom_v3_happy_path_disk_and_cli(tmp_path: Path) -> None:
    man = _valid_sbom_v3_manifest(tmp_path=tmp_path)
    rec = {"schema": "engine-receipt/1", "verdict": "MATCH", "oracle": {"exit_code": 0}}
    mp, rp = tmp_path / "sbom_v3_manifest.json", tmp_path / "rec.json"
    mp.write_text(json.dumps(man), encoding="utf-8")
    rp.write_text(json.dumps(rec), encoding="utf-8")
    res = verify_gold_sbom_v3_file(mp, rp, policy=GoldSbomV3Policy(check_on_disk=True))
    assert res.ok and res.repos_verified == 15 and res.sbom_files_verified == 30 and res.total_components >= 259
    assert sbom_main([str(mp), "--receipt", str(rp), "--check-on-disk"]) == 0
    (tmp_path / "spdx/repo_01.spdx.json").write_text('{"spdxVersion":"SPDX-2.3","license":"FSL-1.1-MIT"}', encoding="utf-8")
    assert sbom_main([str(mp), "--check-on-disk"]) == 2


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (lambda m: m["osi_policy_audit"].update({"stale_fsl_in_sboms": 1}), "osi_policy_violation:stale_fsl"),
        (lambda m: m["repositories"][1].update({"license": "FSL-1.1-MIT"}), "disallowed_license"),
        (lambda m: m.update({"gold_standard_score": "164/165"}), "gold_score_incomplete"),
        (lambda m: m.update({"spdx_version": "SPDX-2.2"}), "invalid_spdx_version"),
        (lambda m: m.update({"cyclonedx_version": "1.4"}), "invalid_cyclonedx_version"),
        (lambda m: m["repositories"][0].update({"commit_sha": "short"}), "invalid_commit_sha"),
        (lambda m: m["repositories"][2].update({"spdx_sha256": "deadbeef"}), "invalid_spdx_sha256"),
        (lambda m: m["repositories"].pop(), "repo_count_mismatch"),
    ],
)
def test_oss_gold_sbom_v3_planted_attacks_fail_closed(mutator: Any, expected: str) -> None:
    man = _valid_sbom_v3_manifest()
    mutator(man)
    res = verify_gold_sbom_v3_bundle(parse_sbom_v3_manifest(man))
    assert not res.ok and res.verdict == "REJECT"
    assert any(expected in e for e in res.errors), res.errors


def test_adversarial_400_trial_fuzz_zero_bypasses() -> None:
    rng = random.Random(20261127)
    quic_bypasses = 0
    for trial in range(200):
        d = _valid_quic_payload()
        kind = trial % 4
        if kind == 0:
            d["packet_numbers"].append(rng.choice([100, 103, 107, 10, -5]))
        elif kind == 1:
            d["firewall_rules"][0]["peer_id"] = rng.choice(["*", "0.0.0.0/0", "::/0", "any", ""])
        elif kind == 2:
            atk = d["attacks"][rng.randrange(4)]
            fld = rng.choice(["rejected", "committed", "error_code", "isas_rejected"])
            atk[fld] = False if fld == "rejected" else (1 if fld == "committed" else (0 if fld == "error_code" else 3))
        else:
            d["binaries"][rng.randrange(5)]["sha256"] = f"zz{trial}"
        if verify_quic_firewall_bundle(parse_quic_payload(d)).ok:
            quic_bypasses += 1
    sbom_bypasses = 0
    for trial in range(200):
        m = _valid_sbom_v3_manifest()
        kind = trial % 4
        if kind == 0:
            m["repositories"][rng.randrange(15)]["license"] = rng.choice(["FSL-1.1-MIT", "PROPRIETARY", "BSL-1.1"])
        elif kind == 1:
            m["osi_policy_audit"][rng.choice(["stale_fsl_in_sboms", "proprietary_in_sboms", "copyleft_in_mit_repos"])] = rng.randint(1, 5)
        elif kind == 2:
            m["repositories"][rng.randrange(15)][rng.choice(["spdx_sha256", "cdx_sha256", "commit_sha"])] = f"bad{trial}"
        else:
            m["repositories"].pop(rng.randrange(15))
        if verify_gold_sbom_v3_bundle(parse_sbom_v3_manifest(m)).ok:
            sbom_bypasses += 1
    assert quic_bypasses == 0 and sbom_bypasses == 0
    assert parse_quic_receipt({"schema": "engine-receipt/1", "verdict": "DRIFT"}).verdict == "DRIFT"
