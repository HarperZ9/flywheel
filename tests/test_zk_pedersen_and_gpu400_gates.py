# SPDX-License-Identifier: MIT
"""Unit, adversarial, and 400-trial fuzz tests for zk_pedersen_attest and gpu_400pack_gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
from typing import Any

import pytest

from harness.gpu_400pack_gate import (
    EXPECTED_KERNELS,
    Gpu400Policy,
    REQUIRED_TARGETS,
    parse_gpu_400pack_bundle,
    verify_gpu_400pack_bundle,
    verify_gpu_400pack_file,
)
from harness.gpu_400pack_gate.pack400_oracle import main as gpu400_main
from harness.zk_pedersen_attest import (
    REQUIRED_CLUSTER_ATTACKS,
    REQUIRED_ISAS,
    REQUIRED_ZK_ATTACKS,
    ZkPedersenPolicy,
    parse_zk_payload,
    parse_zk_receipt,
    rfc6962_mth,
    verify_zk_pedersen_bundle,
    verify_zk_pedersen_file,
)
from harness.zk_pedersen_attest.zk_oracle import main as zk_main


def _hex64(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _valid_zk_payload() -> dict[str, Any]:
    return {
        "mode": "zk_pedersen",
        "schema": "zk-pedersen-bundle/1",
        "verdict": "MATCH",
        "oracle_exit_code": 0,
        "claim_sha256": f"sha256:{_hex64('zkc')}",
        "v_in": 1000,
        "v_out1": 625,
        "v_out2": 375,
        "verified": 1,
        "nums_H_hex": _hex64("H"),
        "c_in_hex": _hex64("cin"),
        "excess_D_hex": _hex64("D"),
        "schnorr_pt_hex": _hex64("sch"),
        "merkle_root_hex": _hex64("mr"),
        "binaries": [
            {"isa": isa, "rel_path": f"out/{isa}.bin", "bytes": 29478 if isa == "wasm" else 84992 + i * 500, "sha256": _hex64(f"zk:{isa}")}
            for i, isa in enumerate(REQUIRED_ISAS)
        ],
        "attacks": [
            {"name": atk, "rejected": True, "committed": 0, "error_code": -101 - i * 100, "isas_rejected": 5}
            for i, atk in enumerate(REQUIRED_ZK_ATTACKS)
        ],
    }


def _valid_cluster_payload() -> dict[str, Any]:
    p_hex = [_hex64(k) for k in ("q", "v", "z", "b")]
    c_root = rfc6962_mth([bytes.fromhex(h) for h in p_hex]).hex()
    return {
        "mode": "cluster_v21",
        "schema": "buildos-v21-cluster/1",
        "verdict": "MATCH",
        "oracle_exit_code": 0,
        "claim_sha256": f"sha256:{_hex64('clc')}",
        "pillars": 4,
        "curve_eqs": 7,
        "quic_root_hex": p_hex[0],
        "vm_root_hex": p_hex[1],
        "zk_merkle_root_hex": p_hex[2],
        "bft_ledger_root_hex": p_hex[3],
        "cluster_root_hex": c_root,
        "binaries": [
            {"isa": isa, "rel_path": f"out/{isa}.bin", "bytes": 66784 if isa == "wasm" else 184320 + i * 500, "sha256": _hex64(f"cl:{isa}")}
            for i, isa in enumerate(REQUIRED_ISAS)
        ],
        "attacks": [
            {"name": atk, "rejected": True, "committed": 0, "error_code": -101 - i * 100, "isas_rejected": 5}
            for i, atk in enumerate(REQUIRED_CLUSTER_ATTACKS)
        ],
    }


def _valid_gpu400_and_rlvr(num_kernels: int = EXPECTED_KERNELS) -> tuple[dict[str, Any], dict[str, Any]]:
    shaders: list[dict[str, Any]] = []
    tb, tr = 0, 0
    for k in range(num_kernels):
        rw = 8 if k < 40 else 7
        for t in REQUIRED_TARGETS:
            sb = 4000 + k * 5
            shaders.append({
                "batch": "wave146a_quadricentennial_400pack",
                "kernel": f"kern_{k:02d}",
                "target": t,
                "shader_bytes": sb,
                "shader_sha256": _hex64(f"s:{k}:{t}"),
                "cert_sha256": _hex64(f"c:{k}:{t}"),
                "rewrites": rw,
                "verify_cert": "PASS",
            })
            tb += sb
            tr += rw
    man = {
        "schema": "buildlang-workstation-gpu-400pack/1",
        "license": "MIT",
        "unique_kernels": num_kernels,
        "total_certified_shaders": len(shaders),
        "total_shader_bytes": tb,
        "total_superopt_rewrites": tr,
        "shaders": shaders,
    }
    cats = {f"cat_{i:02d}": (80 if i < 2 else (64 if i == 2 else 32)) for i in range(28)}
    rlvr = {
        "schema": "jfc3p-14b-oracle-rlvr-pack/12",
        "license": "MIT",
        "total_tasks": 1024,
        "train_tasks": 880,
        "eval_tasks": 144,
        "category_count": 28,
        "categories": cats,
        "artifacts": {
            fn: {"bytes": 1000, "sha256": f"sha256:{_hex64(fn)}"}
            for fn in ("jfc3p_14b_oracle_v12_mit.jsonl", "train_rlvr_v12.jsonl", "eval_rlvr_v12.jsonl", "JFC3P_14B_Oracle_v12_Colab_H100_Ready.ipynb")
        },
    }
    return man, rlvr


def test_zk_cluster_and_gpu400_happy_paths_and_cli(tmp_path: Path) -> None:
    r_zk = verify_zk_pedersen_bundle(parse_zk_payload(_valid_zk_payload()))
    assert r_zk.ok and r_zk.mode == "zk_pedersen" and r_zk.total_attack_rejections == 20
    r_cl = verify_zk_pedersen_bundle(parse_zk_payload(_valid_cluster_payload()), ZkPedersenPolicy(verify_cluster_mth=True))
    assert r_cl.ok and r_cl.mode == "cluster_v21" and r_cl.curve_eqs == 7 and r_cl.total_attack_rejections == 30
    man, rlvr = _valid_gpu400_and_rlvr()
    rec = {"schema": "engine-receipt/1", "verdict": "MATCH", "oracle": {"exit_code": 0}}
    r_g = verify_gpu_400pack_bundle(parse_gpu_400pack_bundle(man, rlvr, rec), Gpu400Policy(require_rlvr_v12=True))
    assert r_g.ok and r_g.shaders_verified == 400 and r_g.unique_kernels == 80 and r_g.rlvr_tasks_verified == 1024
    zp, mp, rp, cp = tmp_path / "zk.json", tmp_path / "gpu.json", tmp_path / "rlvr.json", tmp_path / "rec.json"
    zp.write_text(json.dumps(_valid_zk_payload()), encoding="utf-8")
    mp.write_text(json.dumps(man), encoding="utf-8")
    rp.write_text(json.dumps(rlvr), encoding="utf-8")
    cp.write_text(json.dumps(rec), encoding="utf-8")
    assert verify_zk_pedersen_file(zp).ok and zk_main([str(zp)]) == 0
    assert verify_gpu_400pack_file(mp, rp, cp, Gpu400Policy(require_rlvr_v12=True)).ok
    assert gpu400_main([str(mp), "--rlvr", str(rp), "--receipt", str(cp)]) == 0
    man["license"] = "FSL-1.1-MIT"
    mp.write_text(json.dumps(man), encoding="utf-8")
    assert gpu400_main([str(mp), "--rlvr", str(rp)]) == 2


@pytest.mark.parametrize(
    ("is_cluster", "mutator", "expected"),
    [
        (False, lambda d: d.update({"v_out1": 626}), "value_inflation_breach"),
        (False, lambda d: d.update({"verified": 0}), "zk_proof_not_verified"),
        (False, lambda d: d.update({"schnorr_pt_hex": "bad"}), "invalid_schnorr_pt_hex"),
        (False, lambda d: d["attacks"][0].update({"rejected": False}), "attack_not_rejected"),
        (False, lambda d: d["attacks"][1].update({"committed": 1}), "attack_committed_nonzero"),
        (True, lambda d: d.update({"curve_eqs": 6}), "invalid_curve_eqs"),
        (True, lambda d: d.update({"pillars": 3}), "invalid_cluster_pillars"),
        (True, lambda d: d.update({"cluster_root_hex": _hex64("bad")}), "cluster_rfc6962_mth_mismatch"),
        (True, lambda d: d["attacks"].pop(), "missing_attack"),
        (True, lambda d: d["binaries"].pop(), "missing_isa:wasm"),
    ],
)
def test_zk_and_cluster_planted_attacks_fail_closed(is_cluster: bool, mutator: Any, expected: str) -> None:
    d = _valid_cluster_payload() if is_cluster else _valid_zk_payload()
    mutator(d)
    rep = verify_zk_pedersen_bundle(parse_zk_payload(d), ZkPedersenPolicy(verify_cluster_mth=is_cluster))
    assert not rep.ok and rep.verdict == "REJECT"
    assert any(expected in e for e in rep.errors), rep.errors


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (lambda m, r: m["shaders"][0].update({"verify_cert": "FAIL"}), "uncertified_shader"),
        (lambda m, r: m["shaders"][1].update({"shader_sha256": "zz"}), "invalid_shader_sha256"),
        (lambda m, r: m["shaders"][2].update({"target": "ptx"}), "invalid_target"),
        (lambda m, r: m["shaders"].pop(), "kernel_missing_targets"),
        (lambda m, r: m.update({"license": "PROPRIETARY"}), "non_mit_license"),
        (lambda m, r: r.update({"total_tasks": 1023}), "rlvr_split_mismatch"),
        (lambda m, r: r.update({"license": "FSL-1.1-MIT"}), "rlvr_non_mit_license"),
        (lambda m, r: r["categories"].pop("cat_00"), "rlvr_category_count_mismatch"),
        (lambda m, r: r["artifacts"]["eval_rlvr_v12.jsonl"].update({"sha256": "bad"}), "rlvr_bad_artifact_sha256"),
        (lambda m, r: m.update({"total_superopt_rewrites": 10}), "declared_rewrites_mismatch"),
    ],
)
def test_gpu400_and_rlvr_planted_attacks_fail_closed(mutator: Any, expected: str) -> None:
    man, rlvr = _valid_gpu400_and_rlvr()
    mutator(man, rlvr)
    res = verify_gpu_400pack_bundle(parse_gpu_400pack_bundle(man, rlvr), Gpu400Policy(require_rlvr_v12=True))
    assert not res.ok and res.verdict == "REJECT"
    assert any(expected in e for e in res.errors), res.errors


def test_adversarial_400_trial_fuzz_zero_bypasses() -> None:
    rng = random.Random(20261127)
    zk_bypasses, gpu_bypasses = 0, 0
    for trial in range(200):
        d = _valid_cluster_payload() if (trial % 2 == 0) else _valid_zk_payload()
        kind = trial % 4
        if kind == 0:
            if d["mode"] == "cluster_v21":
                d["curve_eqs"] = rng.choice([0, 3, 6, -1, False])
            else:
                d["v_out1"] = d["v_out1"] + rng.randint(1, 50)
        elif kind == 1:
            atk = d["attacks"][rng.randrange(len(d["attacks"]))]
            fld = rng.choice(["rejected", "committed", "error_code", "isas_rejected"])
            atk[fld] = False if fld == "rejected" else (1 if fld == "committed" else (0 if fld == "error_code" else 2))
        elif kind == 2:
            d["binaries"][rng.randrange(5)]["sha256"] = f"zz{trial}"
        else:
            d["binaries"].pop(rng.randrange(5))
        if verify_zk_pedersen_bundle(parse_zk_payload(d), ZkPedersenPolicy(verify_cluster_mth=True)).ok:
            zk_bypasses += 1
    pol = Gpu400Policy(expected_kernels=4, expected_shaders=20, min_superopt_rewrites=120, require_rlvr_v12=True)
    for trial in range(200):
        m, r = _valid_gpu400_and_rlvr(num_kernels=4)
        kind = trial % 4
        if kind == 0:
            m["shaders"][rng.randrange(20)]["verify_cert"] = "FAIL"
        elif kind == 1:
            m["shaders"][rng.randrange(20)]["shader_sha256"] = f"bad{trial}"
        elif kind == 2:
            r["eval_tasks"] = r["eval_tasks"] - rng.randint(1, 10)
        else:
            r["license"] = rng.choice(["FSL-1.1-MIT", "PROPRIETARY", "BSL-1.1"])
        if verify_gpu_400pack_bundle(parse_gpu_400pack_bundle(m, r), pol).ok:
            gpu_bypasses += 1
    assert zk_bypasses == 0 and gpu_bypasses == 0
    assert parse_zk_receipt({"schema": "engine-receipt/1", "verdict": "DRIFT"}).verdict == "DRIFT"
