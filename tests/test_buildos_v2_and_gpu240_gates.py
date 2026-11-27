# SPDX-License-Identifier: MIT
"""Unit, adversarial, and 400-trial fuzz tests for buildos_v2_attest and gpu_240pack_gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
from typing import Any

import pytest

from harness.buildos_v2_attest import (
    BuildOSV2Policy,
    REQUIRED_ATTACKS,
    REQUIRED_ISAS,
    REQUIRED_SUBSYSTEMS,
    parse_buildos_v2_payload,
    parse_buildos_v2_receipt,
    rfc6962_mth,
    verify_buildos_v2_bundle,
    verify_buildos_v2_file,
)
from harness.buildos_v2_attest.v2_oracle import main as v2_main
from harness.gpu_240pack_gate import (
    EXPECTED_KERNELS,
    Gpu240Policy,
    REQUIRED_TARGETS,
    REQUIRED_VALIDATORS,
    parse_gpu_240pack_manifest,
    verify_gpu_240pack_bundle,
    verify_gpu_240pack_file,
)
from harness.gpu_240pack_gate.pack240_oracle import main as gpu_main


def _hex64(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _valid_v2_payload() -> dict[str, Any]:
    subs = [{"name": s, "digest_hex": _hex64(f"leaf:{s}")} for s in REQUIRED_SUBSYSTEMS]
    root = rfc6962_mth([bytes.fromhex(x["digest_hex"]) for x in subs]).hex()
    return {
        "schema": "buildos-v2-sovereign/1",
        "verdict": "MATCH",
        "oracle_exit_code": 0,
        "claim_sha256": f"sha256:{_hex64('v2claim')}",
        "merkle_root": root,
        "subsystems": subs,
        "binaries": [
            {"isa": isa, "rel_path": f"out/{isa}.bin", "bytes": 134198 if isa == "wasm" else 366592 + i * 1000, "sha256": _hex64(isa)}
            for i, isa in enumerate(REQUIRED_ISAS)
        ],
        "attacks": [
            {"name": atk, "rejected": True, "sovereign_committed": 0, "error_code": -101 - i * 100, "isas_rejected": 5}
            for i, atk in enumerate(REQUIRED_ATTACKS)
        ],
    }


def _valid_gpu240_manifest(num_kernels: int = EXPECTED_KERNELS) -> tuple[dict[str, Any], dict[str, Any]]:
    shaders: list[dict[str, Any]] = []
    total_bytes = 0
    total_rewrites = 0
    for k_idx in range(num_kernels):
        rw = 6 if k_idx < 45 else 5
        for target in REQUIRED_TARGETS:
            sb = 3200 + k_idx * 10
            shaders.append({
                "batch": "wave134a_titan_ai_rlvr_240pack",
                "kernel": f"k_{k_idx:02d}",
                "target": target,
                "shader_bytes": sb,
                "shader_sha256": _hex64(f"s:{k_idx}:{target}"),
                "cert_sha256": _hex64(f"c:{k_idx}:{target}"),
                "rewrites": rw,
                "verify_cert": "PASS",
            })
            total_bytes += sb
            total_rewrites += rw
    manifest = {
        "schema": "buildlang-workstation-gpu-240pack/1",
        "license": "MIT",
        "unique_kernels": num_kernels,
        "total_certified_shaders": len(shaders),
        "total_shader_bytes": total_bytes,
        "total_superopt_rewrites": total_rewrites,
        "shaders": shaders,
    }
    report = {
        "schema": "wave134a-gpu-240pack-ai/1",
        "ok": True,
        "verdict": "PASS",
        "validation_counts": {k: (40 if k == "verify_cert" else 8) for k in REQUIRED_VALIDATORS},
        "planted_controls": {
            "ctrl1_tampered_shader_cert": {"rejected": True, "rc": 1},
            "ctrl2_invalid_shader_msl_syntax": {"rejected": True, "naga_rc": 1},
            "ctrl3_corrupted_spirv_val": {"rejected": True, "rc": 1},
        },
    }
    return manifest, report


def test_buildos_v2_happy_path_and_on_disk_receipt(tmp_path: Path) -> None:
    payload = _valid_v2_payload()
    pol = BuildOSV2Policy(expected_root_prefix=payload["merkle_root"][:16])
    rep = verify_buildos_v2_bundle(parse_buildos_v2_payload(payload), policy=pol)
    assert rep.ok and rep.verdict == "PASS" and rep.subsystems_verified == 12
    assert rep.attacks_verified == 8 and rep.total_attack_rejections == 40
    suffixes = {"x64-pe": ".exe", "x64-elf": ".x64.elf", "rv64-elf": ".rv64.elf", "aarch64-elf": ".aarch64.elf", "wasm": ".wasm"}
    arts = []
    for isa, suf in suffixes.items():
        fp = tmp_path / f"v2{suf}"
        raw = f"zero-c-{isa}".encode("utf-8")
        fp.write_bytes(raw)
        arts.append({"rel_path": fp.name, "bytes": len(raw), "sha256": f"sha256:{hashlib.sha256(raw).hexdigest()}"})
    rec = {
        "schema": "engine-receipt/1",
        "verdict": "MATCH",
        "digests": {"claim_sha256": f"sha256:{_hex64('rec')}"},
        "oracle": {"exit_code": 0, "stdout_excerpt": '"sovereign_root_hex": "b0169274ea5bb300813d8d409c1098cbd92cb7490dcaf'},
        "subject": {"artifacts": arts},
    }
    rec_p = tmp_path / "rec.json"
    rec_p.write_text(json.dumps(rec), encoding="utf-8")
    r_pol = BuildOSV2Policy(require_12_subsystems=False, require_8_attacks=False, verify_rfc6962_mth=False, check_on_disk=True)
    assert verify_buildos_v2_file(rec_p, policy=r_pol, artifact_root=tmp_path).ok
    assert v2_main([str(rec_p), "--receipt-only", "--check-on-disk", "--artifact-root", str(tmp_path)]) == 0
    (tmp_path / "v2.wasm").write_bytes(b"corrupted")
    bad = verify_buildos_v2_file(rec_p, policy=r_pol, artifact_root=tmp_path)
    assert not bad.ok and any("sha256_mismatch:wasm" in e for e in bad.errors)
    assert v2_main([str(rec_p), "--receipt-only", "--check-on-disk", "--artifact-root", str(tmp_path)]) == 2


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (lambda d: d.update({"merkle_root": _hex64("wrong_root")}), "rfc6962_mth_mismatch"),
        (lambda d: d["subsystems"].pop(), "missing_subsystem"),
        (lambda d: d["subsystems"][0].update({"digest_hex": "nothex"}), "invalid_subsystem_digest"),
        (lambda d: d["binaries"].pop(), "missing_isa:wasm"),
        (lambda d: d["binaries"][4].update({"bytes": 999999}), "wasm_exceeds_budget"),
        (lambda d: d["attacks"][0].update({"rejected": False}), "attack_not_rejected"),
        (lambda d: d["attacks"][1].update({"sovereign_committed": 1}), "attack_committed_nonzero"),
        (lambda d: d["attacks"][2].update({"error_code": 0}), "attack_non_negative_code"),
        (lambda d: d["attacks"][3].update({"isas_rejected": 4}), "attack_isa_count_low"),
        (lambda d: d["attacks"].pop(), "missing_attack"),
        (lambda d: d.update({"verdict": "DRIFT"}), "invalid_verdict"),
        (lambda d: d.update({"oracle_exit_code": 2}), "nonzero_oracle_exit"),
    ],
)
def test_buildos_v2_planted_attacks_fail_closed(mutator: Any, expected: str) -> None:
    payload = _valid_v2_payload()
    pol = BuildOSV2Policy(expected_root_prefix="")
    mutator(payload)
    rep = verify_buildos_v2_bundle(parse_buildos_v2_payload(payload), policy=pol)
    assert not rep.ok and rep.verdict == "REJECT"
    assert any(expected in e for e in rep.errors), rep.errors


def test_gpu_240pack_happy_path_and_cli(tmp_path: Path) -> None:
    man, rep_doc = _valid_gpu240_manifest()
    rec = {"schema": "engine-receipt/1", "verdict": "MATCH", "oracle": {"exit_code": 0}}
    pol = Gpu240Policy(require_report_validators=True)
    res = verify_gpu_240pack_bundle(parse_gpu_240pack_manifest(man, rep_doc, rec), policy=pol)
    assert res.ok and res.shaders_verified == 240 and res.unique_kernels == 48 and res.controls_verified == 3
    mp, rp, cp = tmp_path / "m.json", tmp_path / "r.json", tmp_path / "c.json"
    mp.write_text(json.dumps(man), encoding="utf-8")
    rp.write_text(json.dumps(rep_doc), encoding="utf-8")
    cp.write_text(json.dumps(rec), encoding="utf-8")
    assert verify_gpu_240pack_file(mp, rp, cp, policy=pol).ok
    assert gpu_main([str(mp), "--report", str(rp), "--receipt", str(cp)]) == 0
    man["license"] = "FSL-1.1-MIT"
    mp.write_text(json.dumps(man), encoding="utf-8")
    assert gpu_main([str(mp), "--report", str(rp)]) == 2


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (lambda m, r: m["shaders"][0].update({"verify_cert": "FAIL"}), "uncertified_shader"),
        (lambda m, r: m["shaders"][1].update({"shader_sha256": "bad"}), "invalid_shader_sha256"),
        (lambda m, r: m["shaders"][2].update({"target": "cuda"}), "invalid_target"),
        (lambda m, r: m["shaders"].pop(), "kernel_missing_targets"),
        (lambda m, r: m.update({"license": "PROPRIETARY"}), "non_mit_license"),
        (lambda m, r: m.update({"declared_total_bytes": 1, "total_shader_bytes": 1}), "declared_bytes_mismatch"),
        (lambda m, r: r["validation_counts"].update({"dxc": 7}), "validator_count_low:dxc"),
        (lambda m, r: r["planted_controls"]["ctrl1_tampered_shader_cert"].update({"rejected": False}), "control_not_rejected"),
    ],
)
def test_gpu_240pack_planted_attacks_fail_closed(mutator: Any, expected: str) -> None:
    man, rep_doc = _valid_gpu240_manifest()
    mutator(man, rep_doc)
    pol = Gpu240Policy(require_report_validators=True)
    res = verify_gpu_240pack_bundle(parse_gpu_240pack_manifest(man, rep_doc), policy=pol)
    assert not res.ok and res.verdict == "REJECT"
    assert any(expected in e for e in res.errors), res.errors


def test_adversarial_400_trial_fuzz_zero_bypasses() -> None:
    rng = random.Random(20261127)
    v2_pol = BuildOSV2Policy(expected_root_prefix="")
    v2_bypasses = 0
    for trial in range(200):
        d = _valid_v2_payload()
        kind = trial % 4
        if kind == 0:
            d["subsystems"][rng.randrange(12)]["digest_hex"] = _hex64(f"tamper:{trial}")
        elif kind == 1:
            atk = d["attacks"][rng.randrange(8)]
            fld = rng.choice(["rejected", "sovereign_committed", "error_code", "isas_rejected"])
            atk[fld] = False if fld == "rejected" else (1 if fld == "sovereign_committed" else (0 if fld == "error_code" else 3))
        elif kind == 2:
            d["binaries"][rng.randrange(5)]["sha256"] = f"zz{trial}"
        else:
            d["binaries"].pop(rng.randrange(5))
        if verify_buildos_v2_bundle(parse_buildos_v2_payload(d), policy=v2_pol).ok:
            v2_bypasses += 1
    gpu_pol = Gpu240Policy(expected_kernels=4, expected_shaders=20, min_superopt_rewrites=100, require_report_validators=True)
    gpu_bypasses = 0
    for trial in range(200):
        m, r = _valid_gpu240_manifest(num_kernels=4)
        kind = trial % 4
        if kind == 0:
            m["shaders"][rng.randrange(20)]["verify_cert"] = "FAIL"
        elif kind == 1:
            m["shaders"][rng.randrange(20)]["shader_sha256"] = f"bad{trial}"
        elif kind == 2:
            m["shaders"].pop(rng.randrange(20))
        else:
            r["validation_counts"][rng.choice(REQUIRED_VALIDATORS)] = 0
        if verify_gpu_240pack_bundle(parse_gpu_240pack_manifest(m, r), policy=gpu_pol).ok:
            gpu_bypasses += 1
    assert v2_bypasses == 0 and gpu_bypasses == 0
    assert parse_buildos_v2_receipt({"schema": "engine-receipt/1", "verdict": "DRIFT"}).verdict == "DRIFT"
