# SPDX-License-Identifier: MIT
"""Unit, adversarial, and 400-trial fuzz tests for bft_consensus_attest and cap_sandbox_vm_gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
from typing import Any

import pytest

from harness.bft_consensus_attest import (
    BftPolicy,
    REQUIRED_BFT_ATTACKS,
    REQUIRED_ISAS,
    parse_bft_payload,
    parse_bft_receipt,
    rfc6962_mth,
    verify_bft_bundle,
    verify_bft_file,
)
from harness.bft_consensus_attest.bft_oracle import main as bft_main
from harness.cap_sandbox_vm_gate import (
    CAP_CRYPTO,
    CAP_LOG,
    CapVmPolicy,
    REQUIRED_VM_ATTACKS,
    parse_vm_payload,
    parse_vm_receipt,
    verify_cap_vm_bundle,
    verify_cap_vm_file,
)
from harness.cap_sandbox_vm_gate.vm_oracle import main as vm_main


def _hex64(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _sig128(seed: str) -> str:
    return _hex64(seed + ":a") + _hex64(seed + ":b")


def _valid_bft_payload() -> dict[str, Any]:
    leaves = [_hex64(f"blk:{i}") for i in range(4)]
    root = rfc6962_mth([bytes.fromhex(h) for h in leaves]).hex()
    return {
        "schema": "bft-consensus-bundle/1",
        "verdict": "MATCH",
        "oracle_exit_code": 0,
        "claim_sha256": f"sha256:{_hex64('bft_claim')}",
        "nodes": 4,
        "quorum": 3,
        "height": 3,
        "blk3_hex": leaves[3],
        "ledger_root_hex": root,
        "log_leaves_hex": leaves,
        "votes": [
            {"validator_id": v, "height": 3, "block_hash": leaves[3], "sig_hex": _sig128(f"v{v}"), "ed25519_valid": True}
            for v in (0, 1, 2)
        ],
        "binaries": [
            {"isa": isa, "rel_path": f"out/{isa}.bin", "bytes": 30622 if isa == "wasm" else 86528 + i * 1000, "sha256": _hex64(f"bft:{isa}")}
            for i, isa in enumerate(REQUIRED_ISAS)
        ],
        "attacks": [
            {"name": atk, "rejected": True, "committed": 0, "error_code": -101 - i * 100, "isas_rejected": 5}
            for i, atk in enumerate(REQUIRED_BFT_ATTACKS)
        ],
    }


def _valid_vm_payload() -> dict[str, Any]:
    return {
        "schema": "cap-sandbox-vm-bundle/1",
        "verdict": "MATCH",
        "oracle_exit_code": 0,
        "claim_sha256": f"sha256:{_hex64('vm_claim')}",
        "fuel_budget": 512,
        "fuel_used": 447,
        "cap_mask": CAP_CRYPTO | CAP_LOG,
        "guest_sha_hex": _hex64("guest"),
        "trace_sha_hex": _hex64("trace"),
        "vm_root_hex": _hex64("vm_root"),
        "mem_writes": [0, 1, 7, 15, 31],
        "hostcalls": [
            {"hostcall_id": 1, "required_cap": CAP_CRYPTO, "allowed": True},
            {"hostcall_id": 2, "required_cap": CAP_LOG, "allowed": True},
        ],
        "binaries": [
            {"isa": isa, "rel_path": f"out/{isa}.bin", "bytes": 12343 if isa == "wasm" else 34304 + i * 500, "sha256": _hex64(f"vm:{isa}")}
            for i, isa in enumerate(REQUIRED_ISAS)
        ],
        "attacks": [
            {"name": atk, "rejected": True, "committed": 0, "error_code": -101 - i * 100, "isas_rejected": 5}
            for i, atk in enumerate(REQUIRED_VM_ATTACKS)
        ],
    }


def test_bft_and_cap_vm_happy_paths_and_cli(tmp_path: Path) -> None:
    b_rep = verify_bft_bundle(parse_bft_payload(_valid_bft_payload()))
    assert b_rep.ok and b_rep.valid_sigs == 3 and b_rep.attacks_verified == 4 and b_rep.total_attack_rejections == 20
    v_rep = verify_cap_vm_bundle(parse_vm_payload(_valid_vm_payload()))
    assert v_rep.ok and v_rep.fuel_used == 447 and v_rep.attacks_verified == 4 and v_rep.total_attack_rejections == 20
    suffixes = {"x64-pe": ".exe", "x64-elf": ".x64.elf", "rv64-elf": ".rv64.elf", "aarch64-elf": ".aarch64.elf", "wasm": ".wasm"}
    arts = []
    for isa, suf in suffixes.items():
        fp = tmp_path / f"bin{suf}"
        raw = f"zeroc-{isa}".encode("utf-8")
        fp.write_bytes(raw)
        arts.append({"rel_path": fp.name, "bytes": len(raw), "sha256": f"sha256:{hashlib.sha256(raw).hexdigest()}"})
    b_rec = {"schema": "engine-receipt/1", "verdict": "MATCH", "digests": {"claim_sha256": f"sha256:{_hex64('bc')}"}, "oracle": {"exit_code": 0, "stdout_excerpt": json.dumps({"nodes": 4, "quorum": 3, "height": 3, "blk3_hex": _hex64("b3"), "ledger_root_hex": _hex64("lr")})}, "subject": {"artifacts": arts}}
    v_rec = {"schema": "engine-receipt/1", "verdict": "MATCH", "digests": {"claim_sha256": f"sha256:{_hex64('vc')}"}, "oracle": {"exit_code": 0, "stdout_excerpt": json.dumps({"fuel_budget": 512, "fuel_used": 447, "cap_mask": 3, "guest_sha_hex": _hex64("g"), "trace_sha_hex": _hex64("t"), "vm_root_hex": _hex64("vr")})}, "subject": {"artifacts": arts}}
    bp, vp = tmp_path / "bft.json", tmp_path / "vm.json"
    bp.write_text(json.dumps(b_rec), encoding="utf-8")
    vp.write_text(json.dumps(v_rec), encoding="utf-8")
    assert verify_bft_file(bp, policy=BftPolicy(require_4_attacks=False, require_votes=False, verify_rfc6962_mth=False, check_on_disk=True), artifact_root=tmp_path).ok
    assert verify_cap_vm_file(vp, policy=CapVmPolicy(require_4_attacks=False, check_on_disk=True), artifact_root=tmp_path).ok
    assert bft_main([str(bp), "--receipt-only", "--check-on-disk", "--artifact-root", str(tmp_path)]) == 0
    assert vm_main([str(vp), "--receipt-only", "--check-on-disk", "--artifact-root", str(tmp_path)]) == 0
    (tmp_path / "bin.wasm").write_bytes(b"corrupted")
    assert bft_main([str(bp), "--receipt-only", "--check-on-disk", "--artifact-root", str(tmp_path)]) == 2
    assert vm_main([str(vp), "--receipt-only", "--check-on-disk", "--artifact-root", str(tmp_path)]) == 2


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (lambda d: d["votes"].append({"validator_id": 1, "height": 3, "block_hash": _hex64("fork"), "sig_hex": _sig128("f"), "ed25519_valid": True}), "equivocation_double_vote"),
        (lambda d: d["votes"].pop(), "sub_quorum_votes"),
        (lambda d: d["votes"][0].update({"ed25519_valid": False}), "invalid_ed25519_sig"),
        (lambda d: d.update({"ledger_root_hex": _hex64("bad_root")}), "rfc6962_ledger_root_mismatch"),
        (lambda d: d.update({"quorum": 2}), "invalid_bft_quorum"),
        (lambda d: d["attacks"][0].update({"rejected": False}), "bft_attack_not_rejected"),
        (lambda d: d["attacks"][1].update({"committed": 1}), "bft_attack_committed_nonzero"),
        (lambda d: d["attacks"].pop(), "missing_bft_attack"),
        (lambda d: d["binaries"].pop(), "missing_isa:wasm"),
        (lambda d: d.update({"verdict": "DRIFT"}), "invalid_verdict"),
    ],
)
def test_bft_planted_attacks_fail_closed(mutator: Any, expected: str) -> None:
    d = _valid_bft_payload()
    mutator(d)
    rep = verify_bft_bundle(parse_bft_payload(d))
    assert not rep.ok and rep.verdict == "REJECT"
    assert any(expected in e for e in rep.errors), rep.errors


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (lambda d: d.update({"fuel_used": 513}), "fuel_budget_exceeded"),
        (lambda d: d.update({"fuel_budget": 0}), "invalid_fuel_budget"),
        (lambda d: d["mem_writes"].append(32), "oob_linear_memory_write"),
        (lambda d: d["mem_writes"].append(-1), "oob_linear_memory_write"),
        (lambda d: d["mem_writes"].append(1024), "wx_code_write_violation"),
        (lambda d: d["hostcalls"].append({"hostcall_id": 3, "required_cap": 4, "allowed": True}), "unauthorized_hostcall_allowed"),
        (lambda d: d["attacks"][0].update({"rejected": False}), "vm_attack_not_rejected"),
        (lambda d: d["attacks"][1].update({"committed": 1}), "vm_attack_committed_nonzero"),
        (lambda d: d["attacks"].pop(), "missing_vm_attack"),
        (lambda d: d["binaries"].pop(), "missing_isa:wasm"),
    ],
)
def test_cap_vm_planted_attacks_fail_closed(mutator: Any, expected: str) -> None:
    d = _valid_vm_payload()
    mutator(d)
    rep = verify_cap_vm_bundle(parse_vm_payload(d))
    assert not rep.ok and rep.verdict == "REJECT"
    assert any(expected in e for e in rep.errors), rep.errors


def test_adversarial_400_trial_fuzz_zero_bypasses() -> None:
    rng = random.Random(20261127)
    bft_bypasses = 0
    for trial in range(200):
        d = _valid_bft_payload()
        kind = trial % 4
        if kind == 0:
            d["votes"].append({"validator_id": rng.randrange(3), "height": 3, "block_hash": _hex64(f"fk{trial}"), "sig_hex": _sig128(f"fs{trial}"), "ed25519_valid": True})
        elif kind == 1:
            d["votes"][rng.randrange(3)]["ed25519_valid"] = False
        elif kind == 2:
            atk = d["attacks"][rng.randrange(4)]
            fld = rng.choice(["rejected", "committed", "error_code", "isas_rejected"])
            atk[fld] = False if fld == "rejected" else (1 if fld == "committed" else (0 if fld == "error_code" else 3))
        else:
            d["log_leaves_hex"][rng.randrange(4)] = _hex64(f"tamper{trial}")
        if verify_bft_bundle(parse_bft_payload(d)).ok:
            bft_bypasses += 1
    vm_bypasses = 0
    for trial in range(200):
        v = _valid_vm_payload()
        kind = trial % 4
        if kind == 0:
            v["fuel_used"] = rng.randint(513, 2000)
        elif kind == 1:
            v["mem_writes"].append(rng.choice([-1, 32, 64, 1024, 2048]))
        elif kind == 2:
            v["hostcalls"].append({"hostcall_id": 9, "required_cap": rng.choice([4, 8, 16]), "allowed": True})
        else:
            atk = v["attacks"][rng.randrange(4)]
            fld = rng.choice(["rejected", "committed", "error_code", "isas_rejected"])
            atk[fld] = False if fld == "rejected" else (1 if fld == "committed" else (0 if fld == "error_code" else 2))
        if verify_cap_vm_bundle(parse_vm_payload(v)).ok:
            vm_bypasses += 1
    assert bft_bypasses == 0 and vm_bypasses == 0
    assert parse_bft_receipt({"schema": "engine-receipt/1", "verdict": "DRIFT"}).verdict == "DRIFT"
    assert parse_vm_receipt({"schema": "engine-receipt/1", "verdict": "DRIFT"}).verdict == "DRIFT"
